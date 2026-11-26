"""공개 서비스 모드의 안전장치 — 즉석 시연 여행 차단, 요청 한도, 자동 삭제, 실제 LLM 실패 시 템플릿 대체.

인터넷(Cloudflare 터널)에 공개할 때 GPU 작업이 쌓이거나 남의 여행 기록이 오래 남지 않게 하는 장치들이다.
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import demo, retention
from app.adapters.cp19_ai_gateway import ai_gateway
from app.components.cp13_story import StoryGenerator, _plain
from app.config import settings
from app.main import app
from app.models import Job, SessionLocal, Story, Trip
from app.services import place_cache


def tok(n: int) -> dict:
    return {"X-Device-Token": f"public-mode-token-{n:04d}"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _trip_with_photo(client, demo_dir, h) -> str:
    trip = client.post("/api/v1/trips", json={"title": "공개 모드"}, headers=h).json()
    photo = sorted(demo_dir.glob("*.jpg"))[0]
    r = client.post(f"/api/v1/trips/{trip['id']}/photos", files=[("files", (photo.name, photo.read_bytes(), "image/jpeg"))], headers=h)
    assert r.status_code == 200, r.text
    return trip["id"]


def test_seed_and_docs_off_in_public_mode(client, monkeypatch):
    monkeypatch.setattr(settings, "public_mode", True)
    monkeypatch.delenv("DEMO_SEED", raising=False)
    assert client.post("/api/v1/demo/seed", headers=tok(1)).status_code == 404
    meta = client.get("/api/v1/meta").json()
    assert meta["public"] is True and meta["demo_seed"] is False


def test_trip_quota_per_device(client, monkeypatch):
    monkeypatch.setattr(settings, "max_trips_per_day", 2)
    h = tok(2)
    assert [client.post("/api/v1/trips", json={"title": "x"}, headers=h).status_code for _ in range(3)] == [201, 201, 429]
    assert client.post("/api/v1/trips", json={"title": "x"}, headers=tok(3)).status_code == 201  # 다른 기기는 영향 없음


def test_job_capacity(client, monkeypatch, demo_dir):
    """서버 전체 대기 작업이 한도에 차면 503, 한 기기가 작업 2개를 이미 맡겼으면 429 (GPU 작업 쌓임 방지)."""
    h = tok(4)
    trip_id = _trip_with_photo(client, demo_dir, h)
    with SessionLocal() as db:
        busy = [Job(trip_id=trip_id, kind="story", status="queued") for _ in range(2)]
        db.add_all(busy)
        db.commit()
        ids = [j.id for j in busy]
    try:
        monkeypatch.setattr(settings, "max_active_jobs", 2)
        r = client.post(f"/api/v1/trips/{trip_id}/analysis", json={"consent": True}, headers=h)
        assert r.status_code == 503 and "잠시 후" in r.json()["detail"]
        monkeypatch.setattr(settings, "max_active_jobs", 100)
        r = client.post(f"/api/v1/trips/{trip_id}/analysis", json={"consent": True}, headers=h)
        assert r.status_code == 429
        assert client.get(f"/api/v1/trips/{trip_id}", headers=h).json()["status"] == "draft"  # 거절된 요청은 상태를 바꾸지 않음
    finally:
        with SessionLocal() as db:
            for j in ids:
                db.get(Job, j).status = "done"
            db.commit()


def test_retention_purges_only_old_trips(client, monkeypatch):
    monkeypatch.setattr(settings, "retention_days", 3)
    h = tok(5)
    old = client.post("/api/v1/trips", json={"title": "오래됨"}, headers=h).json()["id"]
    new = client.post("/api/v1/trips", json={"title": "새것"}, headers=h).json()["id"]
    with SessionLocal() as db:
        db.get(Trip, old).created_at = datetime.now() - timedelta(days=4)
        db.commit()
    assert retention.purge_expired() >= 1
    assert client.get(f"/api/v1/trips/{old}", headers=h).status_code == 404
    assert client.get(f"/api/v1/trips/{new}", headers=h).status_code == 200


class BrokenLLM:
    """실제 LLM이 형식에 안 맞는 답을 내는 경우를 흉내 낸다."""

    def info(self):
        return {"llm_provider": "ollama", "llm_model": "qwen-test"}

    def llm_story(self, payload):
        return '{"title": "x", "paragraphs": "형식 오류"}'

    def llm_story_part(self, payload):
        return '{"sentences": "형식 오류"}'

    def llm_title(self, payload):
        return '{"title": 3'

    def template_story(self, payload):
        return ai_gateway.template_story(payload)

    def template_paragraph(self, payload, variant):
        return ai_gateway.template_paragraph(payload, variant)


def test_story_falls_back_to_template(client, demo_dir, monkeypatch):
    monkeypatch.setattr(demo, "DEMO_DIR", demo_dir)
    ids = demo.seed_demo_trip("public-mode-token-0006")
    with SessionLocal() as db:
        story = db.get(Story, ids["story_id"])
        StoryGenerator(BrokenLLM(), place_cache).generate(db, story)
        db.commit()
        assert story.status == "ready" and story.model.startswith("템플릿")
        assert all(p["sentences"] for p in story.body) and story.footnotes
        # D-06: 템플릿으로만 쓴 여행기에는 'AI가 … 작성' 문구를 쓰지 않는다
        assert all(p["source"] == "template" for p in story.body)
        assert not story.meta["ai_label"].startswith("AI가") and "공식 데이터 문장" in story.meta["ai_label"]
        assert "AI" not in story.title


class PartLLM(BrokenLLM):
    """날짜별·5곳 단위 호출을 기록하고, 지정한 날만 실패시키는 LLM."""

    def __init__(self, fail_days=()):
        self.calls, self.fail_days = [], set(fail_days)

    def llm_story_part(self, payload):
        self.calls.append((payload["day"], [v["order"] for v in payload["visits"]], payload["first"], payload["last"]))
        if payload["day"] in self.fail_days:
            return '{"sentences": "형식 오류"}'
        return ai_gateway.llm_story_part(payload)  # 모의 LLM 문장

    def llm_title(self, payload):
        return json.dumps({"title": "午時의 부산 여행"}, ensure_ascii=False)  # 한자가 섞인 제목 → 공식 데이터 제목으로


def test_story_written_per_day_in_small_parts(client, demo_dir, monkeypatch):
    """D-04: LLM에는 하루(최대 5곳)씩만 넣는다. 방문지를 빠짐없이, 순서대로 한 번씩 넣는다."""
    monkeypatch.setattr(demo, "DEMO_DIR", demo_dir)
    ids = demo.seed_demo_trip("public-mode-token-0011")
    llm = PartLLM()
    with SessionLocal() as db:
        story = db.get(Story, ids["story_id"])
        StoryGenerator(llm, place_cache).generate(db, story)
        db.commit()
        orders = [o for _, os_, _, _ in sorted(llm.calls) for o in os_]
        assert all(len(os_) <= 5 for _, os_, _, _ in llm.calls)
        assert orders == sorted(orders) and len(orders) == len(set(orders)) == len(story.trip.visits)
        assert sum(1 for c in llm.calls if c[2]) == 1  # 여행 시작 문장은 첫날 첫 부분에만
        assert all(p["source"] == "llm" for p in story.body) and story.meta["ai_label"].startswith("AI가")
        assert story.model == "qwen-test" and "午" not in story.title


def test_failed_day_falls_back_alone(client, demo_dir, monkeypatch):
    """D-04: 한 날짜의 응답만 잘못되면 그날만 템플릿 문단으로 바꾸고, 작성 방식 문구에 그 날짜를 밝힌다 (D-06)."""
    monkeypatch.setattr(demo, "DEMO_DIR", demo_dir)
    ids = demo.seed_demo_trip("public-mode-token-0012")
    with SessionLocal() as db:
        story = db.get(Story, ids["story_id"])
        days = sorted({v.day for v in story.trip.visits})
        assert len(days) >= 2
        StoryGenerator(PartLLM(fail_days={days[-1]}), place_cache).generate(db, story)
        db.commit()
        src = {p["day"]: p["source"] for p in story.body}
        assert src[days[-1]] == "template" and all(src[d] == "llm" for d in days[:-1])
        assert story.model == f"qwen-test + 템플릿 ({days[-1]}일차)"
        assert f"{days[-1]}일차는 AI 응답을 쓰지 못해" in story.meta["ai_label"]


def test_truncated_ollama_reply_is_an_error(monkeypatch):
    """D-04: Ollama가 길이 한도에서 자른 응답(done_reason=length)은 잘린 JSON을 쓰지 않고 실패로 처리한다."""
    from app.adapters import cp19_ai_gateway as gw

    class R:
        status_code, text = 200, ""

        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"sentences": [{"text": "잘린'}, "done_reason": "length"}

    monkeypatch.setattr(gw.httpx, "post", lambda *a, **k: R())
    with pytest.raises(gw.AIError, match="length"):
        gw.ai_gateway._ollama_chat("m", [], {}, {}, 5, "LLM")


def test_template_share_card_not_labeled_ai(client, demo_dir, monkeypatch):
    """D-06: 템플릿으로만 쓴 여행기의 공유 카드에는 'AI가 작성'이라고 쓰지 않는다."""
    from app.api import cp04_story_api

    monkeypatch.setattr(demo, "DEMO_DIR", demo_dir)
    ids = demo.seed_demo_trip("public-mode-token-0013")
    with SessionLocal() as db:
        story = db.get(Story, ids["story_id"])
        StoryGenerator(BrokenLLM(), place_cache).generate(db, story)
        db.commit()
    seen = {}

    def fake_render(*a, **k):
        seen.update(k)
        return b"png"

    monkeypatch.setattr(cp04_story_api, "render_share_card", fake_render)
    client.post(f"/api/v1/stories/{ids['story_id']}/share-card", headers=tok(13))
    assert seen.get("by_ai") is False


class EchoLLM(BrokenLLM):
    """다시 쓰기를 시켜도 이전 문단을 그대로 돌려주는 LLM (실서버 Qwen에서 실제로 관찰됨)."""

    def __init__(self):
        self.variants = []

    def llm_rewrite_paragraph(self, payload, variant):
        self.variants.append(variant)
        return json.dumps({"sentences": [{"text": t, "place_ids": [], "fields": [], "is_fact": False} for t in payload["previous"]]},
                          ensure_ascii=False)

    def template_paragraph(self, payload, variant):
        return ai_gateway.template_paragraph(payload, variant)


def test_rewrite_never_returns_same_paragraph(client, demo_dir, monkeypatch):
    """FR-10: 다시 쓴 문단이 이전과 같으면 시드를 바꿔 한 번 더 묻고, 그래도 같으면 템플릿 문단으로 바꾼다."""
    monkeypatch.setattr(demo, "DEMO_DIR", demo_dir)
    ids = demo.seed_demo_trip("public-mode-token-0009")
    llm = EchoLLM()
    with SessionLocal() as db:
        story = db.get(Story, ids["story_id"])
        before = [s["text"] for s in story.body[0]["sentences"]]
        StoryGenerator(llm, place_cache).rewrite_paragraph(db, story, story.body[0]["id"])
        db.commit()
        after = [s["text"] for s in story.body[0]["sentences"]]
        assert len(llm.variants) == 2 and llm.variants[1] == llm.variants[0] + 1
        assert after and after != before
        assert all(s["footnotes"] for s in story.body[0]["sentences"] if s["is_fact"])
        assert story.body[0]["source"] == "template" and "템플릿" in story.model  # D-06: 다시 쓴 문단도 작성 방식 기록


def test_plain_strips_markdown():
    assert _plain("오늘은 **해운대해수욕장**에 갔어요.") == "오늘은 해운대해수욕장에 갔어요."
    assert _plain("# 1일차") == "1일차"
    assert _plain("시간은 3*4분") == "시간은 3*4분"
    assert _plain("1950 년대 마을, 2 층 식당, 약 1.5 km") == "1950년대 마을, 2층 식당, 약 1.5km"


def test_paragraphs_merged_by_day():
    data = {"paragraphs": [{"day": 1, "sentences": [{"text": "a"}]}, {"day": 1, "sentences": [{"text": "b"}]},
                           {"day": 2, "sentences": [{"text": "c"}]}]}
    out = StoryGenerator._paragraphs(data)
    assert [(p["day"], [s["text"] for s in p["sentences"]]) for p in out] == [(1, ["a", "b"]), (2, ["c"])]


def test_stale_originals_removed_unless_job_active(client, demo_dir):
    """올리고 분석하지 않은 원본(GPS 포함)은 30분이 지나면 지우되, 대기 중인 작업의 원본은 남긴다."""
    import os
    import time as _time

    from app.components.cp17_media_store import media_store

    h = tok(7)
    idle = _trip_with_photo(client, demo_dir, h)
    waiting = _trip_with_photo(client, demo_dir, tok(8))
    old = _time.time() - 3600
    for tid in (idle, waiting):
        os.utime(media_store._orig_dir(tid), (old, old))
    with SessionLocal() as db:
        db.add(Job(trip_id=waiting, kind="analysis", status="queued"))
        db.commit()
    try:
        retention.purge_stale_originals()
        assert media_store.remaining_originals(idle) == 0
        assert media_store.remaining_originals(waiting) == 1
        r = client.post(f"/api/v1/trips/{idle}/analysis", json={"consent": True}, headers=h)
        assert r.status_code == 409 and "다시 올려" in r.json()["detail"]
    finally:
        with SessionLocal() as db:
            for j in db.query(Job).filter(Job.trip_id == waiting):
                j.status = "done"
            db.commit()


def test_long_ai_text_fits_column(client, demo_dir):
    """PostgreSQL은 String(300)을 넘는 값을 거부한다. 실제 VLM의 긴 비교 근거로 분석이 실패했던 경우(위치 없는 사진 추천)."""
    from app.models import Photo

    trip_id = _trip_with_photo(client, demo_dir, tok(9))
    with SessionLocal() as db:
        p = db.query(Photo).filter(Photo.trip_id == trip_id).first()
        p.suggest_reason = "가" * 900
        db.commit()
        db.refresh(p)
        assert len(p.suggest_reason) == 300
