"""시연 보조: 완성된 시연 여행을 한 번에 만든다 (설계 컴포넌트가 아닌 발표용 기능).

합성 시연 사진으로 실제 파이프라인(업로드 → 분석 → 확정 → 여행기)을 그대로 돌리고,
사용자 확인 단계만 AI 추천대로 자동 처리한다. 발표 시간이 부족할 때 결과 화면을 바로 보여 주기 위함.
"""
from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.jobs import run_story_job
from app.models import Job, MatchLog, Photo, SessionLocal, Story, Trip, VisitStatus
from app.services import media_store, orchestrator, repo

DEMO_DIR = settings.data_dir / "demo_photos"


def demo_photo_files() -> list:
    return sorted(DEMO_DIR.glob("*.jpg")) if DEMO_DIR.exists() else []


def seed_demo_trip(owner: str, style: str = "blog") -> dict:
    files = demo_photo_files()
    if not files:
        raise FileNotFoundError("시연 사진이 없어요. scripts/make_demo_photos.py를 먼저 실행해 주세요.")

    # 1) 여행 만들고 사진 올리기 (원본은 임시 저장 → 분석 후 삭제)
    with SessionLocal() as db:
        trip = repo.create_trip(db, owner, "부산 1박 2일 (시연)")
        for f in files:
            p = Photo(trip_id=trip.id, filename=f.name)
            db.add(p)
            db.flush()
            media_store.save_original(trip.id, p.id, f.read_bytes())
        trip.consent_at, trip.status = datetime.now(), "analyzing"
        job = Job(trip_id=trip.id, kind="analysis", detail={})
        db.add(job)
        db.commit()
        trip_id, job_id = trip.id, job.id

    # 2) 분석 파이프라인 실행 (작업 큐 대신 바로 실행)
    orchestrator.run(job_id)

    # 3) 확인 단계 자동 처리: 확인필요·선택필요는 AI 추천으로 확정, 위치 없는 사진은 추천 방문지에 배정
    with SessionLocal() as db:
        trip = db.get(Trip, trip_id)
        for v in trip.visits:
            if VisitStatus(v.status).is_final:
                continue
            if v.ai_place_id:
                v.status, v.place_id = VisitStatus.CONFIRMED.value, v.ai_place_id
            else:
                v.status, v.place_id = VisitStatus.OTHER_PLACE.value, None
            db.add(MatchLog(visit_id=v.id, event="user", ai_place_id=v.ai_place_id, confidence=v.confidence,
                            user_place_id=v.place_id or "other"))
        for p in trip.photos:
            if p.assign_state == "pending":
                if p.suggested_visit_id:
                    p.visit_id, p.assign_state = p.suggested_visit_id, "assigned"
                else:
                    p.assign_state = "skipped"
        repo.refresh_trip_status(trip)
        story = Story(trip_id=trip.id, style=style, status="generating")
        db.add(story)
        db.flush()
        sjob = Job(trip_id=trip.id, kind="story", target_id=story.id, stage="queued")
        db.add(sjob)
        db.commit()
        story_id, story_job_id = story.id, sjob.id

    # 4) 여행기 생성
    run_story_job(story_job_id)
    return {"trip_id": trip_id, "story_id": story_id}
