"""데이터 모델 (요구사항분석서 7장 DR-01~06, DR-09) + 작업 상태(Job).

기본은 SQLite, DATABASE_URL을 주면 PostgreSQL에서도 같은 모델로 동작한다 (설계서 2.5).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


def new_id() -> str:
    return uuid.uuid4().hex[:16]


class VisitStatus(str, Enum):
    """방문지 상태 (DR-02, 설계서 2.4 상태 다이어그램)."""
    ANALYZING = "분석중"
    AUTO_CONFIRMED = "자동확정"
    NEEDS_CHECK = "확인필요"
    NEEDS_SELECTION = "선택필요"
    CONFIRMED = "확정"
    OTHER_PLACE = "기타장소"

    @property
    def is_final(self) -> bool:
        return self in (VisitStatus.AUTO_CONFIRMED, VisitStatus.CONFIRMED, VisitStatus.OTHER_PLACE)


class Base(DeclarativeBase):
    pass


class Trip(Base):  # DR-01
    __tablename__ = "trips"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_token: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # draft → analyzing → review(확인 필요) → ready(확정 완료)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    visits: Mapped[list["Visit"]] = relationship(back_populates="trip", cascade="all, delete-orphan", order_by="Visit.order")
    photos: Mapped[list["Photo"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    stories: Mapped[list["Story"]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="trip", cascade="all, delete-orphan")


class Place(Base):  # DR-03
    """공공데이터 장소는 출처·갱신일과 함께 캐시. 카카오 장소는 원본 ID·place_url만 저장 (카카오 운영정책)."""
    __tablename__ = "places"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # "tour:126508", "busan:B001", "kakao:123"
    source: Mapped[str] = mapped_column(String(16))
    source_id: Mapped[str] = mapped_column(String(48))
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    overview: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    place_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)  # usetime 등 추가 필드
    updated_at: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 제공처 갱신일
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Visit(Base):  # DR-02
    __tablename__ = "visits"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    day: Mapped[int] = mapped_column(Integer)
    date: Mapped[str] = mapped_column(String(10))
    start_at: Mapped[datetime] = mapped_column(DateTime)
    end_at: Mapped[datetime] = mapped_column(DateTime)
    center_lat: Mapped[float | None] = mapped_column(Float, nullable=True)  # 소수점 4자리
    center_lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    rep_photo_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(10), default=VisitStatus.ANALYZING.value)
    place_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_place_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ai_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 후보: [{place_id, distance_m}] — 카카오 후보도 ID·거리만 (이름은 화면 표시 때 실시간 조회)
    candidates: Mapped[list] = mapped_column(JSON, default=list)
    search_radius_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)  # 선택필요 사유 등

    trip: Mapped[Trip] = relationship(back_populates="visits")
    photos: Mapped[list["Photo"]] = relationship(back_populates="visit", foreign_keys="Photo.visit_id")
    match_logs: Mapped[list["MatchLog"]] = relationship(back_populates="visit", cascade="all, delete-orphan")

    @property
    def status_enum(self) -> VisitStatus:
        return VisitStatus(self.status)


class Photo(Base):  # DR-04
    __tablename__ = "photos"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    visit_id: Mapped[str | None] = mapped_column(ForeignKey("visits.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(200))
    taken_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    has_gps: Mapped[bool] = mapped_column(Boolean, default=False)
    # 사진 좌표는 방문지 중심 좌표 계산 후 삭제 (DR-08). 분석 중에만 값이 있다
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lng: Mapped[float | None] = mapped_column(Float, nullable=True)
    thumb_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    # 위치 없는 사진 배정 (FR-06): 추천 방문지, 이유, 사용자 확인 여부
    suggested_visit_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    suggest_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    assign_state: Mapped[str] = mapped_column(String(12), default="none")  # none | pending | assigned | skipped
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    trip: Mapped[Trip] = relationship(back_populates="photos")
    visit: Mapped[Visit | None] = relationship(back_populates="photos", foreign_keys=[visit_id])


class Story(Base):  # DR-05
    __tablename__ = "stories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    style: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(12), default="generating")  # generating | ready | failed
    # 본문: [{id, day, sentences: [{id, text, place_ids, fields, is_fact, footnotes, warnings, edited}]}]
    body: Mapped[list] = mapped_column(JSON, default=list)
    route_summary: Mapped[list] = mapped_column(JSON, default=list)
    # AI 작성 표시 문구, 사실 대조로 뺀 문장, 본문 장소 링크용 이름 목록 (UI-07)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(32), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    trip: Mapped[Trip] = relationship(back_populates="stories")
    footnotes: Mapped[list["Footnote"]] = relationship(back_populates="story", cascade="all, delete-orphan", order_by="Footnote.num")


class Footnote(Base):  # DR-06
    __tablename__ = "footnotes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="CASCADE"), index=True)
    num: Mapped[int] = mapped_column(Integer)
    place_id: Mapped[str] = mapped_column(String(64))
    field: Mapped[str] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(100))
    updated_at: Mapped[str | None] = mapped_column(String(10), nullable=True)
    label: Mapped[str] = mapped_column(String(200), default="")

    story: Mapped[Story] = relationship(back_populates="footnotes")


class MatchLog(Base):  # DR-09 — 정확도 측정용, 사진·좌표 없음
    __tablename__ = "match_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_id: Mapped[str] = mapped_column(ForeignKey("visits.id", ondelete="CASCADE"), index=True)
    event: Mapped[str] = mapped_column(String(12))  # ai | user
    ai_place_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_place_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    visit: Mapped[Visit] = relationship(back_populates="match_logs")


class Job(Base):
    """분석·여행기 작업 상태. 클라이언트가 2초마다 조회한다 (AD-06, UI-01~03)."""
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))  # analysis | story
    target_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # story id
    status: Mapped[str] = mapped_column(String(12), default="queued")  # queued | running | done | failed
    stage: Mapped[str] = mapped_column(String(20), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # 단계별 요약 문구, 사진 수 등
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    trip: Mapped[Trip] = relationship(back_populates="jobs")


_connect_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)

if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):  # 동시 읽기·쓰기(API + 워커 스레드)와 외래 키 연쇄 삭제
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(engine)
