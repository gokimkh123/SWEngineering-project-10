"""API 응답 형식 변환."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.components.cp05_route import OTHER_COLOR, TYPE_COLORS
from app.components.cp13_story import STYLES
from app.components.cp16_place_cache import PlaceCache
from app.models import Job, Photo, Story, Trip, Visit, VisitStatus

STAGE_LABELS = {"exif": "촬영 정보 읽기", "cluster": "방문지 묶기", "match": "장소 찾기", "finalize": "동선·여행기 준비"}
STAGE_ORDER = ["exif", "cluster", "match", "finalize"]


def place_brief(rec) -> dict | None:
    if rec is None:
        return None
    return {"place_id": rec.place_id, "name": rec.name, "type": rec.type, "source": rec.source,
            "source_name": rec.source_name, "color": TYPE_COLORS.get(rec.type or "", OTHER_COLOR), "sample": rec.sample}


def visit_out(db: Session, cache: PlaceCache, v: Visit) -> dict:
    place = cache.resolve(db, v.place_id, v.center_lat, v.center_lng) if v.place_id else None
    ai_place = cache.resolve(db, v.ai_place_id, v.center_lat, v.center_lng) if v.ai_place_id else None
    status = VisitStatus(v.status)
    return {
        "id": v.id, "order": v.order, "day": v.day, "date": v.date,
        "start": v.start_at.strftime("%H:%M"), "end": v.end_at.strftime("%H:%M"),
        "status": status.value, "final": status.is_final,
        "needs_user": status in (VisitStatus.NEEDS_CHECK, VisitStatus.NEEDS_SELECTION),
        "place": place_brief(place),
        "ai": {"place": place_brief(ai_place), "confidence": v.confidence, "reason": v.ai_reason} if (v.ai_place_id or v.ai_reason) else None,
        "photo_ids": [p.id for p in sorted(v.photos, key=lambda p: p.taken_at or datetime.min)],
        "photo_count": len(v.photos), "rep_photo_id": v.rep_photo_id, "note": v.note,
        "center": {"lat": v.center_lat, "lng": v.center_lng} if v.center_lat is not None else None,
        "search_radius_m": v.search_radius_m,
    }


def photo_out(p: Photo) -> dict:
    return {"id": p.id, "filename": p.filename, "taken_at": p.taken_at.isoformat() if p.taken_at else None,
            "has_gps": p.has_gps, "visit_id": p.visit_id, "suggested_visit_id": p.suggested_visit_id,
            "suggest_reason": p.suggest_reason, "assign_state": p.assign_state, "thumb_ready": p.thumb_ready}


def trip_out(t: Trip, latest_jobs: dict[str, Job | None] | None = None) -> dict:
    visits = t.visits
    counts = {s.value: 0 for s in VisitStatus}
    for v in visits:
        counts[v.status] += 1
    cover = next((v.rep_photo_id for v in visits if v.rep_photo_id), None) or next((p.id for p in t.photos if p.thumb_ready), None)
    out = {
        "id": t.id, "title": t.title, "status": t.status, "start_date": t.start_date, "end_date": t.end_date,
        "photo_count": len(t.photos), "visit_count": len(visits), "status_counts": counts,
        "needs_user": counts[VisitStatus.NEEDS_CHECK.value] + counts[VisitStatus.NEEDS_SELECTION.value],
        "pending_photos": sum(1 for p in t.photos if p.assign_state == "pending"),
        "cover_photo_id": cover, "consented": t.consent_at is not None, "created_at": t.created_at.isoformat(),
        "stories": [{"id": s.id, "title": s.title, "status": s.status, "style": s.style} for s in t.stories],
    }
    if latest_jobs is not None:
        out["jobs"] = {k: (job_out(j) if j else None) for k, j in latest_jobs.items()}
    return out


def job_out(j: Job) -> dict:
    eta = None
    if j.status == "running" and j.started_at and j.progress > 0.05:
        elapsed = (datetime.now() - j.started_at).total_seconds()
        eta = max(1, round(elapsed / j.progress * (1 - j.progress)))
    stages = []
    if j.kind == "analysis":
        cur = STAGE_ORDER.index(j.stage) if j.stage in STAGE_ORDER else (len(STAGE_ORDER) if j.status == "done" else -1)
        for i, key in enumerate(STAGE_ORDER):
            state = "done" if (i < cur or j.status == "done") else ("running" if i == cur and j.status == "running" else "pending")
            stages.append({"key": key, "label": STAGE_LABELS[key], "state": state})
    return {"id": j.id, "trip_id": j.trip_id, "kind": j.kind, "target_id": j.target_id, "status": j.status,
            "stage": j.stage, "progress": j.progress, "eta_seconds": eta, "stages": stages,
            "detail": j.detail or {}, "error": j.error}


def story_out(s: Story) -> dict:
    t = s.trip
    date_range = ""
    if t.start_date:
        date_range = t.start_date.replace("-", ".")[5:] + ("–" + t.end_date.replace("-", ".")[5:] if t.end_date and t.end_date != t.start_date else "")
    return {
        "id": s.id, "trip_id": s.trip_id, "style": s.style, "style_label": STYLES.get(s.style, s.style),
        "title": s.title, "status": s.status, "error": s.error, "paragraphs": s.body or [],
        "footnotes": [{"num": f.num, "place_id": f.place_id, "field": f.field, "source_name": f.source_name,
                       "updated_at": f.updated_at, "label": f.label} for f in s.footnotes],
        "route_summary": s.route_summary or [], "meta": s.meta or {}, "model": s.model,
        "prompt_version": s.prompt_version, "date_range": date_range, "visit_count": len(t.visits),
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }
