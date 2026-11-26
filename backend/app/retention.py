"""주기 정리 (API 프로세스 한 곳에서 15분마다).

1) 원본 사진: 올리고 분석하지 않은 채 30분 넘게 남은 원본(GPS 포함)을 지운다. 대기·실행 중인 작업의 여행은 제외 (QA-04, NFR-04)
2) 여행: 만든 지 RETENTION_DAYS가 지난 여행을 썸네일·방문지·여행기·파일까지 지운다. 0이면 끔(로컬 시연 기본값)
인터넷에 공개한 서버에 다른 사람의 사진·여행 기록을 오래 두지 않기 위함 (개인정보 최소 보관).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from app.config import settings
from app.models import Job, SessionLocal, Trip

log = logging.getLogger("chalkak.retention")
INTERVAL_S = 900
ACTIVE = ("queued", "running")


def purge_expired(now: datetime | None = None) -> int:
    """보관 기간이 지난 여행을 지운다(분석·여행기 작업이 진행 중인 여행은 다음 차례로 미룸). 반환: 지운 여행 수."""
    if settings.retention_days <= 0:
        return 0
    from app.services import repo

    cutoff = (now or datetime.now()) - timedelta(days=settings.retention_days)
    n = 0
    with SessionLocal() as db:
        for t in db.query(Trip).filter(Trip.created_at < cutoff).all():
            if any(j.status in ("queued", "running") for j in t.jobs):
                continue
            repo.delete_trip(db, t)
            n += 1
    if n:
        log.info("보관 기간(%s일)이 지난 여행 %d개 삭제", settings.retention_days, n)
    return n


def purge_stale_originals() -> int:
    """분석을 시작하지 않은 채 남은 원본 사진 정리. 대기·실행 중인 작업이 있는 여행의 원본은 남긴다."""
    from app.components.cp17_media_store import media_store

    with SessionLocal() as db:
        active = {tid for (tid,) in db.query(Job.trip_id).filter(Job.status.in_(ACTIVE)).distinct()}
    n = media_store.cleanup_orphans(active)
    if n:
        log.info("오래 남은 원본 사진 폴더 %d개 삭제", n)
    return n


def start() -> None:
    def loop() -> None:
        while True:
            for task in (purge_stale_originals, purge_expired):
                try:
                    task()
                except Exception:  # 다음 주기에 다시 시도
                    log.exception("주기 정리 실패: %s", task.__name__)
            time.sleep(INTERVAL_S)

    threading.Thread(target=loop, name="retention", daemon=True).start()
