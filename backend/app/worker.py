"""RQ 워커 진입점 (설계서 2.5 배포 구조의 worker 컨테이너).

REDIS_URL이 설정된 경우에만 쓴다. 실행: python -m app.worker
"""
from __future__ import annotations

from redis import Redis
from rq import Queue, SimpleWorker

from app.config import settings
from app.models import engine, init_db

WORKER_TTL = 60  # 대기 주기 = TTL - 15 = 45초, 소켓 제한 = 대기 + 10 = 55초


def main() -> None:
    if not settings.redis_url:
        raise SystemExit("REDIS_URL이 없어요. 프로토타입 기본 모드에서는 API 서버가 작업을 직접 처리합니다.")
    init_db()
    engine.dispose()  # 시작 때 쓴 DB 연결은 버리고 작업에서 새로 연다
    conn = Redis.from_url(settings.redis_url)
    # 작업마다 프로세스를 복제하지 않는 워커: DB 연결 풀·불러온 모듈을 재사용하고, 작업을 한 번에 하나씩 처리(GPU 한 작업씩)
    # D-05: RQ 기본값(작업 대기 405초, 소켓 제한 = 대기 + 10초)은 여유가 2.4%뿐이다. 이 서버(Docker Desktop·WSL2)에서는
    # 소켓 시간 초과가 약 3% 일찍 나서(실측: 415초 설정 → 401.5초) 대기 중인 워커가 6분 40초마다 종료됐다.
    # 대기 45초·소켓 55초(여유 18%)로 줄인다. 작업 중에는 RQ가 작업 제한 시간만큼 워커 TTL을 따로 늘린다.
    SimpleWorker([Queue("chalkak", connection=conn)], connection=conn, worker_ttl=WORKER_TTL).work(with_scheduler=False)


if __name__ == "__main__":
    main()
