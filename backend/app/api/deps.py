"""API 공통 의존성: DB 세션, 익명 기기 토큰 (AD-07), 공개 서비스 요청 한도."""
from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Job, SessionLocal, Trip

ACTIVE = ("queued", "running")
MAX_JOBS_PER_DEVICE = 2  # 한 기기가 동시에 맡길 수 있는 분석·여행기 작업 수

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def device_token(x_device_token: str | None = Header(default=None)) -> str:
    """요청 헤더의 익명 기기 토큰으로 여행 소유자를 구분한다 (회원 기능 없음)."""
    if not x_device_token or not TOKEN_RE.match(x_device_token):
        raise HTTPException(401, "기기 토큰이 없어요. 앱을 새로고침해 주세요.")
    return x_device_token


def token_from_query(t: str = Query(..., min_length=16, max_length=64)) -> str:
    """<img> 태그처럼 헤더를 못 붙이는 요청용 (썸네일)."""
    if not TOKEN_RE.match(t):
        raise HTTPException(401, "기기 토큰이 올바르지 않아요")
    return t


def ensure_capacity(db: Session, owner: str) -> None:
    """GPU 작업(분석·여행기)이 끝없이 쌓이지 않게 서버 전체·기기별 대기 작업 수를 제한한다 (NFR-08)."""
    active = db.query(Job).filter(Job.status.in_(ACTIVE))
    if active.count() >= settings.max_active_jobs:
        raise HTTPException(503, "지금 분석 요청이 많아요. 잠시 후 다시 시도해 주세요.")
    if active.join(Trip).filter(Trip.owner_token == owner).count() >= MAX_JOBS_PER_DEVICE:
        raise HTTPException(429, "진행 중인 작업이 끝난 뒤에 다시 시도해 주세요.")


def ensure_trip_quota(db: Session, owner: str) -> None:
    """기기 하나가 하루에 만드는 여행 수 제한 (공개 서비스 남용 방지)."""
    since = datetime.now() - timedelta(days=1)
    n = db.query(Trip).filter(Trip.owner_token == owner, Trip.created_at >= since).count()
    if n >= settings.max_trips_per_day:
        raise HTTPException(429, f"여행은 하루에 {settings.max_trips_per_day}개까지 만들 수 있어요. 내일 다시 시도해 주세요.")
