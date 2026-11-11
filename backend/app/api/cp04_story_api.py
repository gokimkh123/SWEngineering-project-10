"""CP-04 Story API (Application 계층) — IF-04.

책임: 여행기 생성·다시 쓰기 작업 등록, 편집 저장과 사실 대조 경고, 공유 카드 요청 (FR-09~11, UC-06~09).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import jobs
from app.adapters.cp19_ai_gateway import AIError
from app.api.deps import device_token, get_db
from app.api.serializers import story_out
from app.components.cp06_share_card import render_share_card
from app.components.cp13_story import STYLES, StoryNotReady
from app.components.cp15_repository import NotFound
from app.components.cp17_media_store import media_store
from app.models import Job, Story, VisitStatus
from app.services import repo, story_generator

router = APIRouter(tags=["IF-04 Story"])


class StoryCreate(BaseModel):
    style: str = "blog"


class SentenceEdit(BaseModel):
    sentence_id: str
    text: str


class StoryPatch(BaseModel):
    title: str | None = None
    edits: list[SentenceEdit] = []


def _story(db: Session, story_id: str, owner: str) -> Story:
    try:
        return repo.get_story(db, story_id, owner)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.post("/trips/{trip_id}/stories", status_code=202)
def create_story(trip_id: str, body: StoryCreate, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """D1 문체 선택 → 여행기 생성 작업 등록 (AD-05)."""
    try:
        t = repo.get_trip(db, trip_id, owner)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    if body.style not in STYLES:
        raise HTTPException(400, "지원하지 않는 문체예요")
    if not t.visits or any(not VisitStatus(v.status).is_final for v in t.visits):
        raise HTTPException(409, "확인이 필요한 방문지를 먼저 확정해 주세요")
    story = Story(trip_id=t.id, style=body.style, status="generating")
    db.add(story)
    db.flush()
    job = Job(trip_id=t.id, kind="story", target_id=story.id, stage="queued")
    db.add(job)
    db.commit()
    jobs.enqueue(job.id)
    return {"story_id": story.id, "job_id": job.id}


@router.get("/trips/{trip_id}/stories")
def list_stories(trip_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    try:
        t = repo.get_trip(db, trip_id, owner)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    return [story_out(s) for s in sorted(t.stories, key=lambda s: s.created_at, reverse=True)]


@router.get("/stories/{story_id}")
def get_story(story_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    return story_out(_story(db, story_id, owner))


@router.patch("/stories/{story_id}")
def edit_story(story_id: str, body: StoryPatch, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """D3 편집 저장: 고친 문장을 공식 데이터와 대조해 경고를 붙인다 (FR-10, UC-07, UC-09)."""
    s = _story(db, story_id, owner)
    if s.status != "ready":
        raise HTTPException(409, "아직 여행기를 만드는 중이에요")
    if body.title is not None and body.title.strip():
        s.title = body.title.strip()[:200]
    if body.edits:
        try:
            story_generator.apply_edits(db, s, [e.model_dump() for e in body.edits])
        except StoryNotReady as e:
            raise HTTPException(409, str(e)) from e
    db.commit()
    return story_out(s)


@router.post("/stories/{story_id}/paragraphs/{paragraph_id}/rewrite")
def rewrite_paragraph(story_id: str, paragraph_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """문단 다시 쓰기 (FR-10). 실패하면 기존 문단을 유지하고 안내한다 (UC-07 2a)."""
    s = _story(db, story_id, owner)
    try:
        story_generator.rewrite_paragraph(db, s, paragraph_id)
    except KeyError as e:
        raise HTTPException(404, "문단을 찾을 수 없어요") from e
    except (AIError, StoryNotReady) as e:
        db.rollback()
        raise HTTPException(502, f"다시 쓰지 못했어요. 기존 문단을 그대로 둘게요 ({e})") from e
    db.commit()
    return story_out(s)


@router.post("/stories/{story_id}/share-card")
def share_card(story_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """D4 공유 카드 PNG — 좌표·정확한 위치 정보 없음 (FR-11, AC-10)."""
    s = _story(db, story_id, owner)
    if s.status != "ready":
        raise HTTPException(409, "여행기를 먼저 완성해 주세요")
    out = story_out(s)
    first = next((v for v in sorted(s.trip.visits, key=lambda v: v.order) if v.rep_photo_id), None)
    thumb = media_store.read_thumb(first.rep_photo_id) if first else None
    try:
        png = render_share_card(s.title, out["date_range"] + f" · 방문지 {out['visit_count']}곳", s.route_summary, thumb)
    except Exception as e:  # pragma: no cover
        raise HTTPException(500, "공유 카드를 만들지 못했어요. 다시 시도해 주세요") from e
    media_store.card_path(s.id).write_bytes(png)
    return Response(png, media_type="image/png",
                    headers={"Content-Disposition": f'inline; filename="chalkak-{s.id}.png"', "Cache-Control": "no-store"})
