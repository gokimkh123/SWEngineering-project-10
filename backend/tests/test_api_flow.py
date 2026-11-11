"""통합·인수 테스트 — 업로드 → 분석 파이프라인 → 확정 → 동선 → 여행기 → 공유 카드 → 삭제.

외부 API·AI는 샘플 데이터와 모의 어댑터로 대체한다 (계획서 8.1 통합 테스트, 설계서 QA-08).
각 테스트 이름의 AC 번호는 요구사항분석서 9장 인수 기준이다.
"""
import io
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.adapters.cp18_place_data import PlaceSourceError, place_adapter
from app.components import cp08_exif
from app.components.cp17_media_store import media_store
from app.main import app
from app.models import MatchLog, Photo, SessionLocal, Visit

TOKEN = "test-device-token-0001"
OTHER = "test-device-token-0002"
H = {"X-Device-Token": TOKEN}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _files(paths: list[Path]):
    return [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in paths]


def _wait(client, job_id: str, timeout: float = 60) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/v1/jobs/{job_id}", headers=H).json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError("작업이 끝나지 않음")


def _new_trip_with_demo(client, demo_dir) -> str:
    trip = client.post("/api/v1/trips", json={"title": "테스트 여행"}, headers=H).json()
    photos = sorted(demo_dir.glob("*.jpg"))
    r = client.post(f"/api/v1/trips/{trip['id']}/photos", files=_files(photos), headers=H)
    assert r.status_code == 200, r.text
    return trip["id"]


@pytest.fixture(scope="module")
def analyzed(client, demo_dir):
    trip_id = _new_trip_with_demo(client, demo_dir)
    t0 = time.time()
    job_id = client.post(f"/api/v1/trips/{trip_id}/analysis", json={"consent": True}, headers=H).json()["job_id"]
    job = _wait(client, job_id)
    return {"trip_id": trip_id, "job": job, "elapsed": time.time() - t0}


# ---------------------------------------------------------------- 업로드·동의
def test_ac01_upload_limits(client, demo_dir):
    trip = client.post("/api/v1/trips", json={}, headers=H).json()
    photos = sorted(demo_dir.glob("*.jpg"))
    gif = io.BytesIO()
    Image.new("RGB", (8, 8)).save(gif, "GIF")
    files = _files(photos) + [("files", ("anim.gif", gif.getvalue(), "image/gif"))]
    r = client.post(f"/api/v1/trips/{trip['id']}/photos", files=files, headers=H).json()
    assert len(r["accepted"]) == 24 and [x["filename"] for x in r["rejected"]] == ["anim.gif"]
    # 31장 이상은 차단
    r = client.post(f"/api/v1/trips/{trip['id']}/photos", files=_files(photos[:7]), headers=H)
    assert r.status_code == 400 and "30장" in r.json()["detail"]


def test_ac09_consent_required(client, demo_dir):
    trip_id = _new_trip_with_demo(client, demo_dir)
    r = client.post(f"/api/v1/trips/{trip_id}/analysis", json={"consent": False}, headers=H)
    assert r.status_code == 400
    assert media_store.remaining_originals(trip_id) == 24  # 분석 전에는 아무것도 처리하지 않음


def test_other_device_cannot_see_trip(client, analyzed):
    assert client.get(f"/api/v1/trips/{analyzed['trip_id']}", headers={"X-Device-Token": OTHER}).status_code == 404
    assert client.get("/api/v1/trips", headers={}).status_code == 401


# ---------------------------------------------------------------- 분석 결과
def test_ac01_ac08_analysis_summary(analyzed):
    job = analyzed["job"]
    assert job["status"] == "done", job
    assert job["detail"]["exif"] == {"total": 24, "with_gps": 21, "without_gps": 3, "no_info": 0}
    assert job["detail"]["cluster"]["visits"] == 6 and job["detail"]["cluster"]["per_day"] == [5, 1]
    assert analyzed["elapsed"] < 60  # NFR-01 (모의 AI 기준)


def test_ac03_ac05_routing(client, analyzed):
    data = client.get(f"/api/v1/trips/{analyzed['trip_id']}/visits", headers=H).json()
    visits = data["visits"]
    statuses = [v["status"] for v in visits]
    # 시연 세트는 세 상태가 모두 나오게 구성했다 (모의 VLM 기준 4/1/1 — 실제 VLM으로 바꾸면 개수는 달라질 수 있음)
    assert all(statuses.count(s) >= 1 for s in ("자동확정", "확인필요", "선택필요"))
    # 확인필요·선택필요만 사용자에게 묻는다
    assert sum(v["needs_user"] for v in visits) == statuses.count("확인필요") + statuses.count("선택필요")
    for v in visits:
        cands = client.get(f"/api/v1/visits/{v['id']}/candidates", headers=H).json()["candidates"]
        assert 1 <= len(cands) <= 3 and all(c["source_name"] and c["distance_m"] <= 600 for c in cands)


def test_ac09_privacy_after_analysis(client, analyzed):
    trip_id = analyzed["trip_id"]
    assert media_store.remaining_originals(trip_id) == 0  # 원본·VLM 축소본 삭제
    with SessionLocal() as db:
        photos = db.query(Photo).filter(Photo.trip_id == trip_id).all()
        assert all(p.lat is None and p.lng is None for p in photos)  # 사진 좌표 삭제
        logs = db.query(MatchLog).join(Visit).filter(Visit.trip_id == trip_id).all()
        assert logs and all(not hasattr(l, "lat") for l in logs)
    for p in photos:
        r = client.get(f"/api/v1/photos/{p.id}/thumb", params={"t": TOKEN})
        assert r.status_code == 200 and not cp08_exif.has_location_exif(r.content)


def test_ac05_ac13_user_confirmation(client, analyzed, demo_labels):
    trip_id = analyzed["trip_id"]
    data = client.get(f"/api/v1/trips/{trip_id}/visits", headers=H).json()
    check = next(v for v in data["visits"] if v["status"] == "확인필요")
    select = next(v for v in data["visits"] if v["status"] == "선택필요")
    # 확인필요: AI 추천 확정
    r = client.put(f"/api/v1/visits/{check['id']}/place", json={"place_id": check["ai"]["place"]["place_id"]}, headers=H)
    assert r.json()["visit"]["status"] == "확정"
    # 선택필요: 직접 검색으로 확정
    found = client.get("/api/v1/places/search", params={"q": "돼지국밥", "visit_id": select["id"]}, headers=H).json()["results"]
    assert found and found[0]["name"].endswith("돼지국밥")
    r = client.put(f"/api/v1/visits/{select['id']}/place", json={"place_id": found[0]["place_id"]}, headers=H)
    assert r.json()["visit"]["status"] == "확정"
    with SessionLocal() as db:
        assert db.query(MatchLog).filter(MatchLog.event == "user").count() >= 2
    # 위치 없는 사진 3장: 추천 방문지와 이유, 확인 시 배정 (AC-13)
    visits_by_order = {v["order"]: v["id"] for v in data["visits"]}
    label_to_order = {"V1": 1, "V2": 2, "V3": 3, "V4": 4, "V5": 5, "V6": 6}
    truth = {p["file"]: visits_by_order[label_to_order[p["visit"]]] for p in demo_labels["photos"] if not p["has_gps"]}
    assert len(data["untagged"]) == 3
    for u in data["untagged"]:
        assert u["suggest_reason"] and u["suggested_visit_id"] == truth[u["filename"]]
        r = client.put(f"/api/v1/photos/{u['id']}/visit", json={"visit_id": u["suggested_visit_id"]}, headers=H)
        assert r.json()["photo"]["assign_state"] == "assigned"
    assert r.json()["trip"]["status"] == "ready"


def test_ac06_route(client, analyzed):
    trip_id = analyzed["trip_id"]
    full = client.get(f"/api/v1/trips/{trip_id}/route", headers=H).json()
    assert len(full["pins"]) == 6 and [d["count"] for d in full["days"]] == [5, 1]
    day1 = client.get(f"/api/v1/trips/{trip_id}/route", params={"day": 1}, headers=H).json()
    assert [p["order"] for p in day1["pins"]] == [1, 2, 3, 4, 5] and len(day1["legs"]) == 4
    assert all(p["color"].startswith("#") for p in day1["pins"])


def test_ac14_place_detail(client, analyzed):
    visits = client.get(f"/api/v1/trips/{analyzed['trip_id']}/visits", headers=H).json()["visits"]
    tour = next(v for v in visits if v["place"]["source"] == "tour")
    d = client.get(f"/api/v1/places/{tour['place']['place_id']}", params={"visit_id": tour["id"]}, headers=H).json()
    assert d["overview"] and d["address"] and d["source_name"] and d["updated_at"]
    kakao = next(v for v in visits if v["place"]["source"] == "kakao")
    d = client.get(f"/api/v1/places/{kakao['place']['place_id']}", params={"visit_id": kakao["id"]}, headers=H).json()
    assert d["realtime"] and d["name"] and d["address"]
    with SessionLocal() as db:  # 카카오 장소는 DB에 이름·주소를 저장하지 않음 (운영정책)
        from app.models import Place
        row = db.get(Place, kakao["place"]["place_id"])
        assert row is not None and row.name is None and row.address is None


def test_ac17_nearby(client, analyzed):
    groups = client.get(f"/api/v1/trips/{analyzed['trip_id']}/nearby", headers=H).json()["groups"]
    visited = {v["place"]["place_id"] for v in client.get(f"/api/v1/trips/{analyzed['trip_id']}/visits", headers=H).json()["visits"]}
    g1 = groups[0]
    assert 2 <= len(g1["items"]) <= 3
    assert [i["distance_m"] for i in g1["items"]] == sorted(i["distance_m"] for i in g1["items"])
    assert all(i["place_id"] not in visited and i["source"] in ("tour", "busan") for g in groups for i in g["items"])


# ---------------------------------------------------------------- 여행기
@pytest.fixture(scope="module")
def story(client, analyzed):
    r = client.post(f"/api/v1/trips/{analyzed['trip_id']}/stories", json={"style": "blog"}, headers=H)
    assert r.status_code == 202, r.text
    job = _wait(client, r.json()["job_id"])
    assert job["status"] == "done", job
    return client.get(f"/api/v1/stories/{r.json()['story_id']}", headers=H).json()


def test_ac07_story_sources(client, analyzed, story):
    visits = client.get(f"/api/v1/trips/{analyzed['trip_id']}/visits", headers=H).json()["visits"]
    confirmed = {v["place"]["place_id"] for v in visits if v["place"]}
    sents = [s for p in story["paragraphs"] for s in p["sentences"]]
    facts = [s for s in sents if s["is_fact"]]
    assert facts and all(s["footnotes"] for s in facts)  # 사실 문장 출처 100% (NFR-03)
    assert all(set(s["place_ids"]) <= confirmed for s in sents)  # 확정 장소만 등장
    nums = {f["num"] for f in story["footnotes"]}
    assert all(set(s["footnotes"]) <= nums for s in facts)
    assert story["meta"]["ai_label"] and story["route_summary"][0]["day"] == 1


def test_story_requires_confirmed_visits(client, demo_dir):
    trip_id = _new_trip_with_demo(client, demo_dir)
    _wait(client, client.post(f"/api/v1/trips/{trip_id}/analysis", json={"consent": True}, headers=H).json()["job_id"])
    r = client.post(f"/api/v1/trips/{trip_id}/stories", json={"style": "blog"}, headers=H)
    assert r.status_code == 409  # 확인필요 방문지가 남아 있음


def test_fr10_edit_and_rewrite(client, story):
    sid = story["id"]
    target = story["paragraphs"][0]["sentences"][0]
    r = client.patch(f"/api/v1/stories/{sid}", json={"edits": [
        {"sentence_id": target["id"], "text": "해운대 블루라인파크 해변열차는 오후 9시까지 운행한다."}]}, headers=H).json()
    edited = next(s for p in r["paragraphs"] for s in p["sentences"] if s["id"] == target["id"])
    assert edited["edited"] and edited["warnings"][0]["code"] == "time_mismatch"
    before = [s["text"] for s in r["paragraphs"][1]["sentences"]]
    r = client.post(f"/api/v1/stories/{sid}/paragraphs/{r['paragraphs'][1]['id']}/rewrite", headers=H)
    assert r.status_code == 200
    after = r.json()["paragraphs"][1]["sentences"]
    assert [s["text"] for s in after] != before and all(s["footnotes"] for s in after if s["is_fact"])


def test_ac10_share_card(client, story):
    r = client.post(f"/api/v1/stories/{story['id']}/share-card", headers=H)
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(r.content)) as im:
        assert im.size == (1080, 1350)
        assert not im.getexif() and "exif" not in im.info


# ---------------------------------------------------------------- 장애·삭제
def test_ac16_partial_failure(client, demo_dir, monkeypatch):
    """외부 API 장애 모의: 서면 근처 조회만 실패 → 그 방문지만 선택필요, 나머지는 끝까지 진행."""
    original = place_adapter.kakao_nearby

    def flaky(lat, lng, radius):
        if abs(lat - 35.1579) < 0.003 and abs(lng - 129.0596) < 0.003:
            raise PlaceSourceError("kakao 장애(모의)")
        return original(lat, lng, radius)

    monkeypatch.setattr(place_adapter, "kakao_nearby", flaky)
    trip_id = _new_trip_with_demo(client, demo_dir)
    job = _wait(client, client.post(f"/api/v1/trips/{trip_id}/analysis", json={"consent": True}, headers=H).json()["job_id"])
    assert job["status"] == "done"
    visits = client.get(f"/api/v1/trips/{trip_id}/visits", headers=H).json()["visits"]
    failed = [v for v in visits if v["note"] and "불러오지 못했어요" in v["note"]]
    assert len(failed) == 1 and failed[0]["order"] == 3 and failed[0]["status"] == "선택필요"
    assert sum(v["status"] == "자동확정" for v in visits) == 4


def test_ac09_delete_trip(client, demo_dir):
    trip_id = _new_trip_with_demo(client, demo_dir)
    _wait(client, client.post(f"/api/v1/trips/{trip_id}/analysis", json={"consent": True}, headers=H).json()["job_id"])
    with SessionLocal() as db:
        photo_ids = [p.id for p in db.query(Photo).filter(Photo.trip_id == trip_id)]
    assert all(media_store.thumb_path(pid).exists() for pid in photo_ids)
    assert client.delete(f"/api/v1/trips/{trip_id}", headers=H).status_code == 204
    assert client.get(f"/api/v1/trips/{trip_id}", headers=H).status_code == 404
    with SessionLocal() as db:
        assert db.query(Photo).filter(Photo.trip_id == trip_id).count() == 0
        assert db.query(Visit).filter(Visit.trip_id == trip_id).count() == 0
    assert not any(media_store.thumb_path(pid).exists() for pid in photo_ids)


def test_demo_seed(client, demo_dir, monkeypatch):
    """시연 보조: 완성된 시연 여행이 한 번에 만들어지고 여행기까지 준비된다."""
    from app import demo

    monkeypatch.setattr(demo, "DEMO_DIR", demo_dir)
    r = client.post("/api/v1/demo/seed", headers=H)
    assert r.status_code == 201, r.text
    ids = r.json()
    trip = client.get(f"/api/v1/trips/{ids['trip_id']}", headers=H).json()
    assert trip["status"] == "ready" and trip["visit_count"] == 6 and trip["pending_photos"] == 0
    story = client.get(f"/api/v1/stories/{ids['story_id']}", headers=H).json()
    assert story["status"] == "ready" and story["footnotes"]
    assert media_store.remaining_originals(ids["trip_id"]) == 0
