"""RQ 워커 진입점 (설계서 2.5 배포 구조의 worker 컨테이너).

REDIS_URL이 설정된 경우에만 쓴다. 실행: python -m app.worker
"""
from __future__ import annotations

from redis import Redis
from rq import Queue, Worker

from app.config import settings
from app.models import init_db


def main() -> None:
    if not settings.redis_url:
        raise SystemExit("REDIS_URL이 없어요. 프로토타입 기본 모드에서는 API 서버가 작업을 직접 처리합니다.")
    init_db()
    conn = Redis.from_url(settings.redis_url)
    Worker([Queue("chalkak", connection=conn)], connection=conn).work()


if __name__ == "__main__":
    main()
