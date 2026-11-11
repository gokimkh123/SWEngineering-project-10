"""작업 큐 (AD-02: 사진 분석·여행기 생성은 작업 큐 + 워커로 비동기 처리).

- REDIS_URL이 있으면 RQ 큐에 넣고 별도 워커(`python -m app.worker`)가 처리한다 (설계서 2.5 배포 구조).
- 없으면 API 프로세스 안의 스레드 풀이 처리한다 (외부 서비스 없이 실행하는 프로토타입 기본값).
어느 쪽이든 작업 상태는 DB의 Job에 기록되므로 클라이언트 조회(GET /jobs/{id}) 방식은 같다.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.adapters.cp19_ai_gateway import AIError
from app.components.cp13_story import StoryNotReady
from app.config import settings
from app.models import Job, SessionLocal, Story

log = logging.getLogger("chalkak.jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="worker")


def enqueue(job_id: str) -> None:
    if settings.redis_url:
        from redis import Redis
        from rq import Queue

        Queue("chalkak", connection=Redis.from_url(settings.redis_url)).enqueue("app.jobs.run_job", job_id, job_timeout=600)
    else:
        _pool.submit(run_job, job_id)


def run_job(job_id: str) -> None:
    from app.services import orchestrator

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        kind = job.kind
    if kind == "analysis":
        orchestrator.run(job_id)
    elif kind == "story":
        run_story_job(job_id)


def run_story_job(job_id: str) -> None:
    """여행기 생성 작업 (AD-05: 분석과 별도 작업)."""
    from app.services import story_generator

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        story = db.get(Story, job.target_id)
        job.status, job.stage, job.progress, job.started_at = "running", "story", 0.2, datetime.now()
        db.commit()
        try:
            story_generator.generate(db, story)
            job.status, job.progress = "done", 1.0
        except (AIError, StoryNotReady) as e:
            story.status, story.error = "failed", str(e)[:300]
            job.status, job.error = "failed", str(e)[:300]
        except Exception as e:  # pragma: no cover - 예기치 못한 오류도 안내 후 재시도 가능하게
            log.exception("story failed")
            story.status, story.error = "failed", "여행기를 만들지 못했어요"
            job.status, job.error = "failed", str(e)[:300]
        job.finished_at = datetime.now()
        db.commit()
