"""CP-05 Route Service (Domain 공용 모듈 — API·워커 공용).

책임: 날짜별 동선, 이동 시간(직선 거리 × 보정 계수), 타임라인 계산 (FR-07, UC-04).
기타 장소는 방문지 중심 좌표를 쓴다. 보정 계수·속도는 PoC 후 확정 (설계서 3.1).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.geo import haversine_m

DETOUR_FACTOR = 1.3  # 직선 거리 → 실제 이동 거리 보정
WALK_LIMIT_M = 1500
WALK_KMH = 4.5
TRANSIT_KMH = 22.0
TRANSIT_OVERHEAD_MIN = 8  # 대기·환승

TYPE_COLORS = {  # UI-06: 지도 핀은 장소 유형별 색
    "바다": "#2F80ED", "공원": "#1E9E6A", "관광지": "#27AE60", "문화마을": "#9B51E0", "시장": "#F2994A",
    "음식점": "#EB5757", "카페": "#A0643C", "거리": "#E2A400", "전시·체험": "#E67E22",
}
OTHER_COLOR = "#8A8F98"


@dataclass
class RouteStop:
    visit_id: str
    order: int
    day: int
    date: str
    start_at: datetime
    end_at: datetime
    lat: float | None
    lng: float | None
    name: str
    type: str | None
    place_id: str | None
    photo_count: int
    rep_photo_id: str | None
    status: str


def load_stops(db, visits, cache) -> list[RouteStop]:
    """방문지 → 동선 정류장. 장소 이름은 캐시(카카오는 실시간)에서, 기타 장소는 중심 좌표를 쓴다."""
    stops = []
    for v in visits:
        rec = cache.resolve(db, v.place_id, v.center_lat, v.center_lng) if v.place_id else None
        if rec is not None:
            name, ptype = rec.name or "이름 없는 장소", rec.type
            lat = rec.lat if rec.lat is not None else v.center_lat
            lng = rec.lng if rec.lng is not None else v.center_lng
        else:
            name = "기타 장소" if v.status == "기타장소" else f"방문지 {v.order}"
            ptype, lat, lng = None, v.center_lat, v.center_lng
        stops.append(RouteStop(
            visit_id=v.id, order=v.order, day=v.day, date=v.date, start_at=v.start_at, end_at=v.end_at,
            lat=lat, lng=lng, name=name, type=ptype, place_id=v.place_id,
            photo_count=sum(1 for p in v.photos), rep_photo_id=v.rep_photo_id, status=v.status,
        ))
    return stops


def travel_estimate(lat1: float, lng1: float, lat2: float, lng2: float) -> dict:
    straight = haversine_m(lat1, lng1, lat2, lng2)
    dist = straight * DETOUR_FACTOR
    if dist <= WALK_LIMIT_M:
        minutes, mode = dist / 1000 / WALK_KMH * 60, "도보"
    else:
        minutes, mode = dist / 1000 / TRANSIT_KMH * 60 + TRANSIT_OVERHEAD_MIN, "대중교통·차량"
    return {"distance_m": round(dist), "minutes": max(1, round(minutes)), "mode": mode}


def build_route(stops: list[RouteStop], day: int | None = None) -> dict:
    """동선 지도(C1)와 타임라인(C2) 데이터. day가 None이면 전체 보기."""
    stops = sorted(stops, key=lambda s: s.start_at)
    days = sorted({s.day for s in stops})
    selected = [s for s in stops if day is None or s.day == day]
    pins, legs, timeline = [], [], []
    prev = None
    for s in selected:
        color = TYPE_COLORS.get(s.type or "", OTHER_COLOR)
        pin = {"visit_id": s.visit_id, "order": s.order, "day": s.day, "name": s.name, "type": s.type or "기타",
               "color": color, "lat": s.lat, "lng": s.lng, "place_id": s.place_id, "photo_count": s.photo_count,
               "rep_photo_id": s.rep_photo_id, "status": s.status,
               "time_range": f"{s.start_at:%H:%M}–{s.end_at:%H:%M}"}
        pins.append(pin)
        leg = None
        if prev is not None and prev.day == s.day and None not in (prev.lat, prev.lng, s.lat, s.lng):
            leg = {"from": prev.visit_id, "to": s.visit_id, **travel_estimate(prev.lat, prev.lng, s.lat, s.lng)}
            legs.append(leg)
        stay = max(5, round((s.end_at - s.start_at).total_seconds() / 60))
        timeline.append({**pin, "start": s.start_at.strftime("%H:%M"), "end": s.end_at.strftime("%H:%M"),
                         "stay_minutes": stay, "leg_from_prev": leg})
        prev = s
    day_summaries = []
    for d in days:
        ds = [s for s in stops if s.day == d]
        day_summaries.append({"day": d, "date": ds[0].date, "count": len(ds), "photo_count": sum(s.photo_count for s in ds),
                              "time_range": f"{ds[0].start_at:%H:%M}–{ds[-1].end_at:%H:%M}"})
    return {"days": day_summaries, "day": day, "pins": pins, "legs": legs, "timeline": timeline}


def route_summary(stops: list[RouteStop]) -> list[dict]:
    """여행기·공유 카드에 넣는 날짜별 동선 요약 (좌표 없음, FR-09, FR-11)."""
    out = []
    for d in sorted({s.day for s in stops}):
        ds = sorted((s for s in stops if s.day == d), key=lambda s: s.start_at)
        out.append({"day": d, "date": ds[0].date, "time_range": f"{ds[0].start_at:%H:%M}–{ds[-1].end_at:%H:%M}",
                    "stops": [{"order": s.order, "name": s.name, "type": s.type or "기타",
                               "color": TYPE_COLORS.get(s.type or "", OTHER_COLOR), "place_id": s.place_id} for s in ds]})
    return out
