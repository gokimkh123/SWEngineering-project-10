"""CP-02 Trip API (Application 계층) — IF-02.

책임: 여행 생성·삭제, 사진 업로드(형식·개수·크기 검증), 동의 확인 후 분석 작업 등록, 작업 상태 조회
(FR-01~04, NFR-04, UI-01~03).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import jobs
from app.api.deps import device_token, get_db, token_from_query
from app.api.serializers import job_out, photo_out, trip_out
from app.components import cp08_exif
from app.components.cp15_repository import NotFound
from app.components.cp17_media_store import media_store
from app.config import settings
from app.models import Job, Photo
from app.services import repo

router = APIRouter(tags=["IF-02 Trip"])


class TripCreate(BaseModel):
    title: str = ""


class AnalysisRequest(BaseModel):
    consent: bool = False  # AI 분석 동의 (NFR-04, AC-09)


def _trip(db: Session, trip_id: str, owner: str):
    try:
        return repo.get_trip(db, trip_id, owner)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.post("/trips", status_code=201)
def create_trip(body: TripCreate, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    return trip_out(repo.create_trip(db, owner, body.title.strip()[:100]))


@router.get("/trips")
def list_trips(owner: str = Depends(device_token), db: Session = Depends(get_db)):
    return [trip_out(t) for t in repo.list_trips(db, owner)]


@router.get("/trips/{trip_id}")
def get_trip(trip_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    t = _trip(db, trip_id, owner)
    return trip_out(t, {"analysis": repo.latest_job(db, t.id, "analysis"), "story": repo.latest_job(db, t.id, "story")}) | {
        "photos": [photo_out(p) for p in sorted(t.photos, key=lambda p: p.created_at)]}


@router.patch("/trips/{trip_id}")
def rename_trip(trip_id: str, body: TripCreate, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    t = _trip(db, trip_id, owner)
    if body.title.strip():
        t.title = body.title.strip()[:100]
        db.commit()
    return trip_out(t)


@router.delete("/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    t = _trip(db, trip_id, owner)
    if any(j.status in ("queued", "running") for j in t.jobs):
        raise HTTPException(409, "분석이 끝난 뒤에 삭제할 수 있어요")
    repo.delete_trip(db, t)
    return Response(status_code=204)


@router.post("/trips/{trip_id}/photos")
async def upload_photos(trip_id: str, files: list[UploadFile] = File(...), owner: str = Depends(device_token),
                        db: Session = Depends(get_db)):
    """사진 업로드 (FR-01). 30장 초과는 통째로 막고, 형식·크기가 맞지 않는 사진만 빼고 받는다."""
    t = _trip(db, trip_id, owner)
    if t.status != "draft":
        raise HTTPException(409, "이미 분석한 여행에는 사진을 더 올릴 수 없어요")
    if len(t.photos) + len(files) > settings.max_photos:
        raise HTTPException(400, f"사진은 한 여행에 최대 {settings.max_photos}장까지 올릴 수 있어요 "
                                 f"(지금 {len(t.photos)}장 + 선택 {len(files)}장)")
    accepted, rejected = [], []
    for f in files:
        data = await f.read(settings.max_photo_bytes + 1)
        name = (f.filename or "photo")[:200]
        if len(data) > settings.max_photo_bytes:
            rejected.append({"filename": name, "reason": "20MB를 넘는 사진이에요"})
            continue
        try:
            cp08_exif.detect_format(data)
        except cp08_exif.UnsupportedImageError as e:
            rejected.append({"filename": name, "reason": str(e)})
            continue
        p = Photo(trip_id=t.id, filename=name)
        db.add(p)
        db.flush()
        media_store.save_original(t.id, p.id, data)  # 원본은 임시 저장 (분석 후 삭제)
        accepted.append(p)
    db.commit()
    return {"accepted": [photo_out(p) for p in accepted], "rejected": rejected, "total": len(t.photos)}


@router.post("/trips/{trip_id}/analysis", status_code=202)
def start_analysis(trip_id: str, body: AnalysisRequest, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """분석 작업 등록 → job_id (AD-02). 동의가 없으면 시작하지 않는다 (NFR-04)."""
    t = _trip(db, trip_id, owner)
    if not body.consent:
        raise HTTPException(400, "사진 AI 분석에 동의해야 분석을 시작할 수 있어요")
    if not t.photos:
        raise HTTPException(409, "먼저 사진을 올려 주세요")
    if t.status != "draft":
        running = repo.latest_job(db, t.id, "analysis")
        if running and running.status in ("queued", "running"):
            return {"job_id": running.id}
        raise HTTPException(409, "이미 분석한 여행이에요")
    if media_store.remaining_originals(t.id) == 0:
        raise HTTPException(409, "원본 사진이 남아 있지 않아요. 사진을 다시 올려 주세요")
    t.consent_at = datetime.now()
    t.status = "analyzing"
    job = Job(trip_id=t.id, kind="analysis", detail={})
    db.add(job)
    db.commit()
    jobs.enqueue(job.id)
    return {"job_id": job.id}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, owner: str = Depends(device_token), db: Session = Depends(get_db)):
    """진행 상태 조회 (클라이언트가 2초마다 호출, AD-06)."""
    try:
        return job_out(repo.get_job(db, job_id, owner))
    except NotFound as e:
        raise HTTPException(404, str(e)) from e


@router.get("/photos/{photo_id}/thumb")
def get_thumb(photo_id: str, owner: str = Depends(token_from_query), db: Session = Depends(get_db)):
    """EXIF를 제거한 썸네일만 내려준다 (DR-04)."""
    try:
        p = repo.get_photo(db, photo_id, owner)
    except NotFound as e:
        raise HTTPException(404, str(e)) from e
    data = media_store.read_thumb(p.id)
    if data is None:
        raise HTTPException(404, "썸네일이 아직 없어요")
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})
