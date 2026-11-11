"""CP-03 Visit API (Application 계층) — IF-03.

책임: 방문지·후보·AI 근거 조회, 장소 확정·변경·기타 장소, 직접 검색, 위치 없는 사진 배정,
장소 상세(카카오는 실시간 조회), 동선 조회, 근처 못 가본 곳 (FR-05~08, FR-12, UC-02~05).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.cp18_place_data import SOURCE_LICENSES
from app.api.deps import device_token, get_db
from app.api.serializers import photo_out, place_brief, trip_out, visit_out
from app.components.cp05_route import build_route, load_stops
from app.components.cp15_repository import NotFound
from app.geo import haversine_m
from app.models import MatchLog, VisitStatus
from app.services import finder, place_cache, repo

router = APIRouter(tags=["IF-03 Visit"])


class PlaceChoice(BaseModel):
    place_id: str | None = None
    other: bool = False  # "기타 장소"로 저장 (UI-05)


class PhotoAssign(BaseModel):
    visit_id: str | None = None
    skip: bool = False


def _or_404(fn, *args):
    try:
        return fn(*args)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.get("/trips/{trip_id}/visits")
def list_visits(trip_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    t = _or_404(repo.get_trip, db, trip_id, owner)
    untagged = [photo_out(p) for p in sorted(t.photos, key=lambda p: p.taken_at.isoformat() if p.taken_at else "")
                if p.visit_id is None and p.assign_state in ("pending", "skipped")]
    return {"trip": trip_out(t), "visits": [visit_out(db, place_cache, v) for v in repo.visits(db, t.id)], "untagged": untagged}


@router.get("/visits/{visit_id}/candidates")
def visit_candidates(visit_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """B2 장소 확인: 후보마다 거리, 출처, AI 추천·근거 (UI-04)."""
    v = _or_404(repo.get_visit, db, visit_id, owner)
    cands = []
    for c in v.candidates or []:
        rec = place_cache.resolve(db, c["place_id"], v.center_lat, v.center_lng)
        if rec is None:
            continue
        d = rec.to_dict()
        d.update(distance_m=c["distance_m"], ai_pick=(c["place_id"] == v.ai_place_id))
        cands.append(d)
    return {"visit": visit_out(db, place_cache, v), "candidates": cands, "radius_m": v.search_radius_m}


@router.put("/visits/{visit_id}/place")
def choose_place(visit_id: str, body: PlaceChoice, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """사용자 확정·수정 (FR-05). 자동확정도 바꿀 수 있고, 결과는 매칭 로그로 남긴다 (DR-09)."""
    v = _or_404(repo.get_visit, db, visit_id, owner)
    if v.status == VisitStatus.ANALYZING.value:
        raise HTTPException(409, "아직 분석 중인 방문지예요")
    if body.other:
        v.status, v.place_id = VisitStatus.OTHER_PLACE.value, None
    else:
        if not body.place_id:
            raise HTTPException(400, "장소를 골라 주세요")
        rec = place_cache.resolve(db, body.place_id, v.center_lat, v.center_lng)
        if rec is None:
            raise HTTPException(404, "장소 정보를 찾을 수 없어요")
        place_cache.upsert(db, rec)  # 공공데이터는 캐시, 카카오는 ID·URL만
        v.status, v.place_id = VisitStatus.CONFIRMED.value, rec.place_id
    db.add(MatchLog(visit_id=v.id, event="user", ai_place_id=v.ai_place_id, confidence=v.confidence,
                    user_place_id=v.place_id if not body.other else "other"))
    repo.refresh_trip_status(v.trip)
    db.commit()
    return {"visit": visit_out(db, place_cache, v), "trip": trip_out(v.trip)}


@router.get("/places/search")
def search_places(q: str = Query(..., min_length=1, max_length=50), visit_id: str | None = None,
                  owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """직접 검색 (UI-05)."""
    lat = lng = None
    if visit_id:
        v = _or_404(repo.get_visit, db, visit_id, owner)
        lat, lng = v.center_lat, v.center_lng
    results = finder.search(db, q, lat, lng)
    out = []
    for c in results:
        d = c.record.to_dict()
        d["distance_m"] = round(c.distance_m) if lat is not None else None
        out.append(d)
    return {"results": out}


@router.get("/places/{place_id}")
def place_detail(place_id: str, visit_id: str | None = None, owner: str = Depends(device_token),
                 db: Session = Depends(get_db)):
    """C3 장소 상세: 공공데이터는 개요·주소·사진·출처·갱신일, 카카오는 실시간 이름·주소와 링크 (FR-08, AC-14)."""
    lat = lng = None
    if visit_id:
        v = _or_404(repo.get_visit, db, visit_id, owner)
        lat, lng = v.center_lat, v.center_lng
    rec = place_cache.resolve(db, place_id, lat, lng)
    if rec is None:
        raise HTTPException(404, "장소 정보를 불러오지 못했어요")
    d = rec.to_dict()
    d["realtime"] = rec.source == "kakao"
    d["license"] = SOURCE_LICENSES.get(rec.source, "")
    return d


@router.put("/photos/{photo_id}/visit")
def assign_photo(photo_id: str, body: PhotoAssign, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """B3 위치 없는 사진 배정 (FR-06). 사용자가 확인해야 배정된다."""
    p = _or_404(repo.get_photo, db, photo_id, owner)
    if body.skip:
        p.visit_id, p.assign_state = None, "skipped"
    else:
        v = _or_404(repo.get_visit, db, body.visit_id or "", owner)
        if v.trip_id != p.trip_id:
            raise HTTPException(400, "같은 여행의 방문지만 고를 수 있어요")
        p.visit_id, p.assign_state = v.id, "assigned"
    repo.refresh_trip_status(p.trip)
    db.commit()
    return {"photo": photo_out(p), "trip": trip_out(p.trip)}


@router.get("/trips/{trip_id}/route")
def trip_route(trip_id: str, day: int | None = None, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """C1 동선 지도·C2 타임라인 (FR-07). day 생략 시 전체 보기."""
    t = _or_404(repo.get_trip, db, trip_id, owner)
    visits = repo.visits(db, t.id)
    return build_route(load_stops(db, visits, place_cache), day)


@router.get("/trips/{trip_id}/nearby")
def nearby(trip_id: str, visit_id: str | None = None, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """C4 근처 못 가본 곳 (FR-12, AC-17): 방문지 주변 미방문 공식 데이터 장소 2~3곳, 거리순."""
    t = _or_404(repo.get_trip, db, trip_id, owner)
    visits = [v for v in repo.visits(db, t.id) if v.center_lat is not None]
    if visit_id:
        visits = [v for v in visits if v.id == visit_id]
    visited = {v.place_id for v in t.visits if v.place_id}
    groups = []
    for v in visits:
        rec = place_cache.resolve(db, v.place_id, v.center_lat, v.center_lng) if v.place_id else None
        lat = rec.lat if rec and rec.lat is not None else v.center_lat
        lng = rec.lng if rec and rec.lng is not None else v.center_lng
        items = []
        for c in finder.nearby_unvisited(db, lat, lng, visited):
            d = place_brief(c.record) | {"distance_m": round(haversine_m(lat, lng, c.record.lat, c.record.lng)),
                                          "lat": c.record.lat, "lng": c.record.lng, "overview": c.record.overview}
            items.append(d)
        groups.append({"visit_id": v.id, "order": v.order, "day": v.day,
                       "name": rec.name if rec else f"방문지 {v.order}", "items": items})
    return {"groups": groups}
