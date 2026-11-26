"""요구사항 명세서 기준 중 11/23 테스트에서 확인하지 못했던 부분 (결과서 5.1 '명세서와 다른 점'의 보완 테스트).

- FR-05 (AC-05): '기타 장소' 저장 → 여행기·동선에 장소 정보 없이 반영
- FR-03 (AC-03): 반경 300m 안에 후보가 없으면 600m로 넓혀 찾기
- FR-01: 위치 정보가 든 실제 HEIC·PNG 파일 업로드와 촬영 정보 추출
- NFR-08: 장소 데이터 캐시 적중률 (같은 지역을 다시 분석하면 외부 장소 API를 다시 부르지 않음)
- NFR-07: 서버 API 키(시험용 가짜 값)가 어떤 응답에도 나오지 않음
"""
import io
import time
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.main import app
from app.models import Photo, SessionLocal
from app.services import finder, place_cache

TOKEN = "spec-gap-token-0001"
H = {"X-Device-Token": TOKEN}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _wait(client, job_id: str, timeout: float = 60) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/v1/jobs/{job_id}", headers=H).json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError("작업이 끝나지 않음")


def _analyze(client, files) -> str:
    trip = client.post("/api/v1/trips", json={"title": "명세서 보완"}, headers=H).json()
    r = client.post(f"/api/v1/trips/{trip['id']}/photos", files=files, headers=H)
    assert r.status_code == 200 and not r.json()["rejected"], r.text
    job = client.post(f"/api/v1/trips/{trip['id']}/analysis", json={"consent": True}, headers=H).json()
    assert _wait(client, job["job_id"])["status"] == "done"
    return trip["id"]


def _demo_files(demo_dir: Path):
    return [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in sorted(demo_dir.glob("*.jpg"))]


def test_ac05_other_place_saved(client, demo_dir):
    """FR-05: 맞는 후보가 없으면 '기타 장소'로 저장 → 장소 정보 없이 확정, 동선·여행기에 반영."""
    trip_id = _analyze(client, _demo_files(demo_dir))
    data = client.get(f"/api/v1/trips/{trip_id}/visits", headers=H).json()
    target = next(v for v in data["visits"] if v["status"] == "선택필요")
    r = client.put(f"/api/v1/visits/{target['id']}/place", json={"other": True}, headers=H)
    assert r.status_code == 200 and r.json()["visit"]["status"] == "기타장소" and r.json()["visit"]["place"] is None
    for v in data["visits"]:  # 나머지 방문지·위치 없는 사진 확정
        if v["id"] != target["id"] and v["needs_user"]:
            client.put(f"/api/v1/visits/{v['id']}/place", json={"place_id": v["ai"]["place"]["place_id"]}, headers=H)
    for u in data["untagged"]:
        client.put(f"/api/v1/photos/{u['id']}/visit", json={"visit_id": u["suggested_visit_id"]}, headers=H)
    route = client.get(f"/api/v1/trips/{trip_id}/route", params={"day": target["day"]}, headers=H).json()
    assert any(t["visit_id"] == target["id"] and not t.get("place_id") for t in route["timeline"])
    job = client.post(f"/api/v1/trips/{trip_id}/stories", json={"style": "blog"}, headers=H).json()
    assert _wait(client, job["job_id"])["status"] == "done"
    story = client.get(f"/api/v1/stories/{job['story_id']}", headers=H).json()
    assert story["status"] == "ready"
    # 기타 장소 문장에는 장소 근거·각주가 없다 (공식 데이터가 없는 곳)
    assert any(not s["place_ids"] and not s["footnotes"] for p in story["paragraphs"] for s in p["sentences"])


def test_fr03_radius_expands_to_600m():
    """FR-03: 반경 300m 안에 공식 후보가 없으면 600m로 넓힌다 (태종대 북쪽 약 450m 지점)."""
    lat, lng = 35.0525 + 450 / 111_320, 129.0857
    with SessionLocal() as db:
        cands, radius = finder.find(db, lat, lng)
    assert radius == 600 and cands and cands[0].record.name.startswith("태종대")
    assert 300 < cands[0].distance_m <= 600


def _exif_bytes(taken: datetime, lat: float, lng: float) -> bytes:
    def dms(deg):
        d = int(deg)
        m = int((deg - d) * 60)
        return (float(d), float(m), round((deg - d - m / 60) * 3600, 2))

    exif = Image.Exif()
    stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
    exif[0x0132] = stamp
    exif.get_ifd(0x8769)[0x9003] = stamp
    exif.get_ifd(0x8825).update({0: b"\x02\x03\x00\x00", 1: "N", 2: dms(lat), 3: "E", 4: dms(lng)})
    return exif.tobytes()


def test_fr01_heic_and_png_with_location(client):
    """FR-01: 휴대폰 원본 형식(HEIC)과 PNG도 접수하고 촬영 시각·위치를 읽는다 (11/23에는 형식 검사만 확인)."""
    pytest.importorskip("pillow_heif")
    import pillow_heif

    pillow_heif.register_heif_opener()
    im = Image.new("RGB", (640, 480), (40, 120, 200))
    heic, png = io.BytesIO(), io.BytesIO()
    im.save(heic, "HEIF", exif=_exif_bytes(datetime(2026, 11, 21, 10, 15), 35.0975, 129.0106), quality=80)
    im.save(png, "PNG", exif=_exif_bytes(datetime(2026, 11, 21, 15, 5), 35.1007, 129.1245))
    trip_id = _analyze(client, [("files", ("IMG_0001.HEIC", heic.getvalue(), "image/heic")),
                                ("files", ("shot.png", png.getvalue(), "image/png"))])
    with SessionLocal() as db:
        photos = db.query(Photo).filter(Photo.trip_id == trip_id).all()
        assert len(photos) == 2 and all(p.has_gps and p.taken_at for p in photos)
    visits = client.get(f"/api/v1/trips/{trip_id}/visits", headers=H).json()["visits"]
    assert len(visits) == 2  # 두 장이 서로 다른 방문지(감천문화마을·오륙도 스카이워크 근처)로 묶임


def test_nfr08_place_cache_hit_rate(client, demo_dir):
    """NFR-08: 같은 지역 사진을 다시 분석하면 후보 조회가 모두 캐시에서 나와 외부 장소 API를 다시 부르지 않는다."""
    _analyze(client, _demo_files(demo_dir))
    before = place_cache.stats()
    _analyze(client, _demo_files(demo_dir))
    after = place_cache.stats()
    assert after["misses"] == before["misses"] and after["hits"] > before["hits"]


def test_nfr07_dummy_server_keys_never_returned(client, monkeypatch):
    """NFR-07: 서버 환경변수의 API 키 값(시험용 가짜 키)이 API 응답·오류 메시지에 나오지 않는다."""
    secret = "fake-value-for-test-only"  # gitleaks:allow (실제 키 아님, 응답에 나오지 않는지 보는 시험용 값)
    for k in ("tour_api_key", "busan_api_key", "kakao_rest_key", "anthropic_api_key", "gemini_api_key"):
        monkeypatch.setattr(settings, k, secret + k)
    responses = [client.get("/api/v1/meta"), client.get("/api/v1/health"), client.get("/api/v1/trips", headers=H),
                 client.get("/api/v1/trips"), client.get("/api/v1/trips/nope", headers=H),
                 client.post("/api/v1/trips/nope/analysis", json={"consent": True}, headers=H)]
    for r in responses:
        assert secret not in r.text, r.request.url
