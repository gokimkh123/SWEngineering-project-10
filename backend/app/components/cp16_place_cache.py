"""CP-16 Place Cache (Data 계층).

책임: 공공데이터 장소를 (출처, 원본 ID)로 저장하고 출처·갱신일 보관. 카카오 결과는 캐시하지 않는다
(장소 ID·place_url만 저장 — 카카오 운영정책, DR-03). 쿼터 절약을 위한 반경 조회 캐시 (NFR-08).
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.cp18_place_data import PlaceDataAdapter, PlaceRecord
from app.geo import haversine_m
from app.models import Place

BUSAN_REFRESH = timedelta(days=1)  # 부산시 목록은 하루 한 번 적재 (DR-07b)
QUERY_TTL = timedelta(hours=24)
KAKAO_MEMO_TTL = timedelta(minutes=10)


class PlaceCache:
    def __init__(self, adapter: PlaceDataAdapter) -> None:
        self.adapter = adapter
        self._query_cache: dict[tuple, tuple[datetime, list[str]]] = {}
        self._lock = threading.Lock()
        self._busan_loaded_at: datetime | None = None
        self._kakao_memo: dict[str, tuple[datetime, PlaceRecord]] = {}
        self.hits = 0
        self.misses = 0

    # ---- 저장 ----
    def upsert(self, db: Session, rec: PlaceRecord) -> Place:
        row = db.get(Place, rec.place_id)
        if row is None:
            row = Place(id=rec.place_id, source=rec.source, source_id=rec.source_id)
            db.add(row)
        if rec.source == "kakao":
            # 운영정책: 카카오 로컬 결과는 장소 ID와 URL만 저장
            row.place_url = rec.place_url
            return row
        row.name, row.type = rec.name, rec.type
        row.lat, row.lng, row.address = rec.lat, rec.lng, rec.address
        if rec.overview:
            row.overview = rec.overview
        if rec.image_url:
            row.image_url = rec.image_url
        extra = dict(row.extra or {})
        if rec.usetime:
            extra["usetime"] = rec.usetime
        extra["sample"] = rec.sample
        row.extra = extra
        row.updated_at = rec.updated_at
        row.fetched_at = datetime.now()
        return row

    def get(self, db: Session, place_id: str) -> Place | None:
        return db.get(Place, place_id)

    @staticmethod
    def to_record(row: Place) -> PlaceRecord:
        extra = row.extra or {}
        return PlaceRecord(
            source=row.source, source_id=row.source_id, name=row.name, type=row.type, lat=row.lat, lng=row.lng,
            address=row.address, overview=row.overview, image_url=row.image_url, place_url=row.place_url,
            usetime=extra.get("usetime"), updated_at=row.updated_at, sample=bool(extra.get("sample")),
        )

    # ---- 부산시 데이터 ----
    def ensure_busan_loaded(self, db: Session) -> None:
        with self._lock:
            if self._busan_loaded_at and datetime.now() - self._busan_loaded_at < BUSAN_REFRESH:
                return
            for rec in self.adapter.busan_all():
                if rec.lat is not None and rec.lng is not None:
                    self.upsert(db, rec)
            db.commit()
            self._busan_loaded_at = datetime.now()

    def busan_nearby(self, db: Session, lat: float, lng: float, radius_m: float) -> list[PlaceRecord]:
        self.ensure_busan_loaded(db)
        rows = db.scalars(select(Place).where(Place.source == "busan")).all()
        return [self.to_record(r) for r in rows if r.lat is not None and haversine_m(lat, lng, r.lat, r.lng) <= radius_m]

    def busan_search(self, db: Session, query: str) -> list[PlaceRecord]:
        self.ensure_busan_loaded(db)
        q = query.replace(" ", "")
        rows = db.scalars(select(Place).where(Place.source == "busan")).all()
        return [self.to_record(r) for r in rows if q and q in (r.name or "").replace(" ", "")]

    # ---- TourAPI 반경 조회 캐시 ----
    def tour_nearby(self, db: Session, lat: float, lng: float, radius_m: int) -> list[PlaceRecord]:
        key = (round(lat, 3), round(lng, 3), radius_m)  # 약 100m 격자
        now = datetime.now()
        with self._lock:
            cached = self._query_cache.get(key)
        if cached and now - cached[0] < QUERY_TTL:
            rows = [db.get(Place, pid) for pid in cached[1]]
            if all(rows):
                self.hits += 1
                return [self.to_record(r) for r in rows]
        self.misses += 1
        recs = self.adapter.tour_nearby(lat, lng, radius_m)
        for rec in recs:
            if rec.lat is not None:
                self.upsert(db, rec)
        db.commit()
        with self._lock:
            self._query_cache[key] = (now, [r.place_id for r in recs if r.lat is not None])
        return [r for r in recs if r.lat is not None]

    # ---- 장소 정보 해석 (화면·여행기용) ----
    def resolve(self, db: Session, place_id: str | None, near_lat: float | None = None,
                near_lng: float | None = None) -> PlaceRecord | None:
        """장소 ID로 표시용 정보를 얻는다.

        공공데이터는 캐시에서(개요가 없으면 상세 조회 후 캐시), 카카오는 이름·주소를 실시간 조회한다.
        카카오 결과는 DB에 넣지 않고 프로세스 메모리에 10분만 둔다 (운영정책: ID·URL 외 저장 금지).
        """
        if not place_id:
            return None
        source, _, source_id = place_id.partition(":")
        row = db.get(Place, place_id)
        if source == "kakao":
            now = datetime.now()
            with self._lock:
                hit = self._kakao_memo.get(place_id)
            if hit and now - hit[0] < KAKAO_MEMO_TTL:
                rec = hit[1]
            else:
                try:
                    rec = self.adapter.kakao_lookup(source_id, near_lat, near_lng)
                except Exception:
                    rec = None
                if rec:
                    with self._lock:
                        self._kakao_memo[place_id] = (now, rec)
            if rec and row and row.place_url:
                rec.place_url = row.place_url
            return rec
        if row is not None:
            rec = self.to_record(row)
            if source == "tour" and not rec.overview:
                try:
                    detail = self.adapter.tour_detail(source_id)
                except Exception:
                    detail = None
                if detail and detail.overview:
                    row.overview = detail.overview
                    db.commit()
                    rec.overview = detail.overview
            return rec
        if source == "tour":
            try:
                rec = self.adapter.tour_detail(source_id)
            except Exception:
                return None
            if rec:
                self.upsert(db, rec)
                db.commit()
            return rec
        return None

    def known_names(self, db: Session) -> dict[str, str]:
        """사실 대조용: 캐시에 있는 공공데이터 장소 이름 → 장소 ID."""
        rows = db.scalars(select(Place).where(Place.name.is_not(None))).all()
        names = {r.name: r.id for r in rows if r.name}
        for rec in self.adapter.sample.records:  # 샘플 모드에서는 샘플 장소 이름도 포함
            names.setdefault(rec.name, rec.place_id)
        return names

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses, "hit_rate": round(self.hits / total, 3) if total else None}
