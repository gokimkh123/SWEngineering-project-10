"""CP-10 Candidate Finder (Domain 공용 모듈 — API·워커 공용).

책임: 반경 300m→600m 후보 조회(TourAPI, 장소 캐시의 부산시 데이터, 카카오 보조), 중복 합치기,
거리순 2~3곳, 키워드 검색 (FR-03, FR-05 직접 검색), 근처 못 가본 곳 추천 (FR-12).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.cp18_place_data import PlaceDataAdapter, PlaceRecord, PlaceSourceError
from app.components.cp16_place_cache import PlaceCache
from app.geo import haversine_m

RADII = (300, 600)  # FR-03
MAX_CANDIDATES = 3
DEDUPE_DIST_M = 150
SOURCE_PRIORITY = {"tour": 0, "busan": 1, "kakao": 2}  # 같은 장소면 공식 관광 데이터 우선
NEARBY_RADIUS_M = 3000  # FR-12 근처 못 가본 곳 탐색 반경 (도보·대중교통 한 정거장 거리)


class CandidateLookupError(RuntimeError):
    """외부 데이터 조회가 재시도 후에도 실패. 해당 방문지만 선택필요로 넘긴다 (AC-16)."""


@dataclass
class Candidate:
    record: PlaceRecord
    distance_m: float

    @property
    def place_id(self) -> str:
        return self.record.place_id

    def to_dict(self) -> dict:
        d = self.record.to_dict()
        d["distance_m"] = round(self.distance_m)
        return d


def _norm(name: str | None) -> str:
    return re.sub(r"[\s()·\-]", "", name or "")


def merge_dedupe(records: list[PlaceRecord], lat: float, lng: float) -> list[Candidate]:
    """같은 장소가 여러 출처에서 나오면 하나로 합친다(이름이 같거나 포함 관계이고 150m 이내)."""
    cands = sorted(
        (Candidate(r, haversine_m(lat, lng, r.lat, r.lng)) for r in records if r.lat is not None and r.lng is not None),
        key=lambda c: (SOURCE_PRIORITY.get(c.record.source, 9), c.distance_m),
    )
    kept: list[Candidate] = []
    for c in cands:
        n = _norm(c.record.name)
        dup = any(
            (n and (n in _norm(k.record.name) or _norm(k.record.name) in n))
            and haversine_m(c.record.lat, c.record.lng, k.record.lat, k.record.lng) <= DEDUPE_DIST_M
            for k in kept
        )
        if not dup:
            kept.append(c)
    return sorted(kept, key=lambda c: c.distance_m)


class CandidateFinder:
    def __init__(self, adapter: PlaceDataAdapter, cache: PlaceCache) -> None:
        self.adapter = adapter
        self.cache = cache

    def _gather(self, db: Session, lat: float, lng: float, radius: int) -> list[PlaceRecord]:
        try:
            recs = self.cache.tour_nearby(db, lat, lng, radius)
            recs += self.cache.busan_nearby(db, lat, lng, radius)
            recs += self.adapter.kakao_nearby(lat, lng, radius)
        except PlaceSourceError as e:
            raise CandidateLookupError(str(e)) from e
        return recs

    def find(self, db: Session, lat: float, lng: float) -> tuple[list[Candidate], int]:
        """후보 2~3곳과 사용한 반경. 600m에도 없으면 빈 목록 (→ 선택필요)."""
        for radius in RADII:
            merged = merge_dedupe(self._gather(db, lat, lng, radius), lat, lng)
            if merged:
                for c in merged[:MAX_CANDIDATES]:
                    self.cache.upsert(db, c.record)  # 카카오는 ID·URL만 저장됨
                db.commit()
                return merged[:MAX_CANDIDATES], radius
        return [], RADII[-1]

    def search(self, db: Session, query: str, lat: float | None = None, lng: float | None = None) -> list[Candidate]:
        """직접 검색 (FR-05, UI-05)."""
        query = query.strip()
        if not query:
            return []
        recs: list[PlaceRecord] = []
        for fn in (lambda: self.adapter.tour_search(query), lambda: self.cache.busan_search(db, query),
                   lambda: self.adapter.kakao_search(query, lat, lng)):
            try:
                recs += fn()
            except PlaceSourceError:
                continue
        if lat is None or lng is None:
            return [Candidate(r, 0.0) for r in recs[:10]]
        out = merge_dedupe(recs, lat, lng)[:10]
        for c in out:
            self.cache.upsert(db, c.record)
        db.commit()
        return out

    def nearby_unvisited(self, db: Session, lat: float, lng: float, exclude: set[str], limit: int = 3) -> list[Candidate]:
        """방문지 주변 공식 데이터 장소 중 이번 여행에서 가지 않은 곳 (FR-12). 카카오 보조 데이터는 제외."""
        try:
            recs = self.cache.tour_nearby(db, lat, lng, NEARBY_RADIUS_M) + self.cache.busan_nearby(db, lat, lng, NEARBY_RADIUS_M)
        except PlaceSourceError:
            return []
        merged = merge_dedupe(recs, lat, lng)
        excluded_names = set()
        for pid in exclude:
            row = self.cache.get(db, pid)
            if row is not None and row.name:
                excluded_names.add(_norm(row.name))
        return [c for c in merged if c.place_id not in exclude and _norm(c.record.name) not in excluded_names][:limit]
