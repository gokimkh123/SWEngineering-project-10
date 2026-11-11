"""API 공통 의존성: DB 세션, 익명 기기 토큰 (AD-07)."""
from __future__ import annotations

import re
from collections.abc import Iterator

from fastapi import Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.models import SessionLocal

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
