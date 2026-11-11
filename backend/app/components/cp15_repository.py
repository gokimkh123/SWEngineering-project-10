"""CP-15 Trip Repository (Data 계층).

책임: 여행·방문지·사진·여행기·각주·매칭 로그 저장, 여행 삭제 시 연쇄 삭제 (DR-01~06, DR-09, NFR-04).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.components.cp17_media_store import MediaStore
from app.models import Job, Photo, Place, Story, Trip, Visit, VisitStatus


class NotFound(LookupError):
    pass


class TripRepository:
    def __init__(self, media: MediaStore) -> None:
        self.media = media

    # ---- Trip ----
    def create_trip(self, db: Session, owner: str, title: str = "") -> Trip:
        trip = Trip(owner_token=owner, title=title or "새 여행기")
        db.add(trip)
        db.commit()
        return trip

    def list_trips(self, db: Session, owner: str) -> list[Trip]:
        return list(db.scalars(select(Trip).where(Trip.owner_token == owner).order_by(Trip.created_at.desc())))

    def get_trip(self, db: Session, trip_id: str, owner: str) -> Trip:
        trip = db.get(Trip, trip_id)
        if trip is None or trip.owner_token != owner:  # 다른 기기의 여행은 없는 것처럼 (AD-07)
            raise NotFound("여행을 찾을 수 없어요")
        return trip

    def delete_trip(self, db: Session, trip: Trip) -> None:
        """여행 삭제 시 방문지·사진·여행기·각주·매칭 로그·작업과 파일을 모두 지운다 (NFR-04, AC-09)."""
        photo_ids = [p.id for p in trip.photos]
        story_ids = [s.id for s in trip.stories]
        db.delete(trip)
        db.commit()
        self.media.delete_trip_media(trip.id, photo_ids, story_ids)

    # ---- Visit / Photo ----
    def get_visit(self, db: Session, visit_id: str, owner: str) -> Visit:
        v = db.get(Visit, visit_id)
        if v is None or v.trip.owner_token != owner:
            raise NotFound("방문지를 찾을 수 없어요")
        return v

    def get_photo(self, db: Session, photo_id: str, owner: str) -> Photo:
        p = db.get(Photo, photo_id)
        if p is None or p.trip.owner_token != owner:
            raise NotFound("사진을 찾을 수 없어요")
        return p

    def visits(self, db: Session, trip_id: str) -> list[Visit]:
        return list(db.scalars(select(Visit).where(Visit.trip_id == trip_id).order_by(Visit.order)))

    def place(self, db: Session, place_id: str | None) -> Place | None:
        return db.get(Place, place_id) if place_id else None

    # ---- Story / Job ----
    def get_story(self, db: Session, story_id: str, owner: str) -> Story:
        s = db.get(Story, story_id)
        if s is None or s.trip.owner_token != owner:
            raise NotFound("여행기를 찾을 수 없어요")
        return s

    def get_job(self, db: Session, job_id: str, owner: str) -> Job:
        j = db.get(Job, job_id)
        if j is None or j.trip.owner_token != owner:
            raise NotFound("작업을 찾을 수 없어요")
        return j

    def latest_job(self, db: Session, trip_id: str, kind: str) -> Job | None:
        return db.scalars(select(Job).where(Job.trip_id == trip_id, Job.kind == kind).order_by(Job.created_at.desc())).first()

    # ---- 상태 ----
    @staticmethod
    def refresh_trip_status(trip: Trip) -> None:
        """방문지·위치 없는 사진이 모두 정리되면 ready, 아니면 review."""
        if trip.status in ("draft", "analyzing"):
            return
        pending_visit = any(not VisitStatus(v.status).is_final for v in trip.visits)
        pending_photo = any(p.assign_state == "pending" for p in trip.photos)
        trip.status = "review" if (pending_visit or pending_photo) else "ready"

    @staticmethod
    def set_trip_dates(trip: Trip) -> None:
        if trip.visits:
            trip.start_date = min(v.date for v in trip.visits)
            trip.end_date = max(v.date for v in trip.visits)
