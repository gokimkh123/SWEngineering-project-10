"""CP-07 Analysis Orchestrator (Analysis 계층, 분석 파이프라인 워커).

책임: EXIF → 군집화 → 후보 → VLM 순서 실행, 진행률 기록, 방문지 단위 실패 격리, 종료 시 원본·좌표 삭제
(UC-01, UC-02, AD-03, QA-01, QA-04, QA-06). 설계서 2.4 시퀀스 다이어그램의 흐름을 그대로 따른다.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from app.adapters.cp19_ai_gateway import AIError
from app.components import cp08_exif, cp09_clusterer
from app.components.cp10_candidates import CandidateFinder, CandidateLookupError
from app.components.cp11_matcher import PlaceMatcher
from app.components.cp12_untagged import UntaggedPhotoResolver, VisitSpan
from app.components.cp15_repository import TripRepository
from app.components.cp16_place_cache import PlaceCache
from app.components.cp17_media_store import MediaStore
from app.models import Job, Photo, SessionLocal, Trip, Visit, VisitStatus

log = logging.getLogger("chalkak.orchestrator")

STAGES = [
    ("exif", "촬영 정보 읽기"),
    ("cluster", "방문지 묶기"),
    ("match", "장소 찾기"),
    ("finalize", "동선·여행기 준비"),
]
# 단계별 진행률 구간 (UI-01)
SPAN = {"exif": (0.0, 0.25), "cluster": (0.25, 0.32), "match": (0.32, 0.92), "finalize": (0.92, 1.0)}
MATCH_WORKERS = 4  # 방문지별 동시 처리 (QA-01)


class AnalysisOrchestrator:
    def __init__(self, repo: TripRepository, media: MediaStore, cache: PlaceCache, finder: CandidateFinder,
                 matcher: PlaceMatcher, resolver: UntaggedPhotoResolver) -> None:
        self.repo, self.media, self.cache = repo, media, cache
        self.finder, self.matcher, self.resolver = finder, matcher, resolver
        self._progress_lock = threading.Lock()

    # ------------------------------------------------------------ 진행률
    def _update(self, job_id: str, stage: str, frac: float, detail: dict | None = None, status: str = "running") -> None:
        with self._progress_lock, SessionLocal() as db:
            job = db.get(Job, job_id)
            lo, hi = SPAN[stage]
            job.stage = stage
            job.progress = round(lo + (hi - lo) * min(1.0, frac), 3)
            job.status = status
            if detail:
                job.detail = {**(job.detail or {}), **detail}
            db.commit()

    # ------------------------------------------------------------ 실행
    def run(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            trip_id = job.trip_id
            job.status, job.started_at = "running", datetime.now()
            db.commit()
        try:
            self._run(job_id, trip_id)
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                job.status, job.stage, job.progress, job.finished_at = "done", "done", 1.0, datetime.now()
                db.commit()
        except Exception as e:  # 작업 전체 실패도 안내하고 재시도할 수 있게 (NFR-08)
            log.exception("analysis failed")
            with SessionLocal() as db:
                job = db.get(Job, job_id)
                job.status, job.error, job.finished_at = "failed", f"분석 중 오류가 발생했어요: {e}"[:300], datetime.now()
                trip = db.get(Trip, trip_id)
                trip.status = "draft"
                db.commit()
        finally:
            self._purge_sensitive(trip_id)

    def _purge_sensitive(self, trip_id: str) -> None:
        """성공·실패와 관계없이 원본 사진과 사진 좌표를 지운다 (DR-08, QA-04, AC-09)."""
        self.media.delete_originals(trip_id)
        with SessionLocal() as db:
            for p in db.query(Photo).filter(Photo.trip_id == trip_id):
                p.lat = p.lng = None
            db.commit()

    def _run(self, job_id: str, trip_id: str) -> None:
        # ---- 1. EXIF (CP-08) ----
        with SessionLocal() as db:
            photos = list(db.query(Photo).filter(Photo.trip_id == trip_id).order_by(Photo.created_at))
            n = len(photos)
            for i, p in enumerate(photos):
                data = self.media.read_original(trip_id, p.id)
                if data is None:
                    continue
                meta = cp08_exif.extract_meta(data)
                p.taken_at, p.has_gps, p.lat, p.lng = meta.taken_at, meta.has_gps, meta.lat, meta.lng
                self.media.save_thumb(p.id, cp08_exif.make_thumbnail(data))
                self.media.save_vlm_image(trip_id, p.id, cp08_exif.make_vlm_image(data))
                p.thumb_ready = True
                db.commit()
                self._update(job_id, "exif", (i + 1) / max(n, 1))
            with_gps = sum(1 for p in photos if p.has_gps)
            no_info = sum(1 for p in photos if not p.has_gps and p.taken_at is None)
            self._update(job_id, "exif", 1.0, {"exif": {"total": n, "with_gps": with_gps, "without_gps": n - with_gps,
                                                        "no_info": no_info}})
            self._update(job_id, "cluster", 0.0)  # 다음 단계 시작 표시 (UI-01)

            # ---- 2. 군집화 (CP-09) ----
            points = [cp09_clusterer.PhotoPoint(p.id, p.taken_at, p.lat, p.lng) for p in photos]
            result = cp09_clusterer.cluster_photos(points)
            db.query(Visit).filter(Visit.trip_id == trip_id).delete()
            for c in result.visits:
                v = Visit(trip_id=trip_id, order=c.order, day=c.day, date=c.date.isoformat(), start_at=c.start_at,
                          end_at=c.end_at, center_lat=c.center_lat, center_lng=c.center_lng, rep_photo_id=c.rep_photo_id,
                          status=VisitStatus.ANALYZING.value)
                db.add(v)
                db.flush()
                for pid in c.photo_ids:
                    if not result.time_only and pid in result.untagged_ids:
                        continue
                    db.get(Photo, pid).visit_id = v.id
            trip = db.get(Trip, trip_id)
            self.repo.set_trip_dates(trip)
            db.commit()
            visit_ids = [v.id for v in self.repo.visits(db, trip_id)]
            days = len({c.day for c in result.visits})
            self._update(job_id, "cluster", 1.0, {
                "cluster": {"visits": len(result.visits), "days": days, "time_only": result.time_only,
                            "per_day": [sum(1 for c in result.visits if c.day == d) for d in range(1, days + 1)]},
                "preview": [{"order": c.order, "day": c.day, "lat": c.center_lat, "lng": c.center_lng,
                             "start": c.start_at.strftime("%H:%M")} for c in result.visits],
            })
            self._update(job_id, "match", 0.0, {"match": {"done": 0, "total": len(result.visits)}})

        # ---- 3. 후보 조회(CP-10) + VLM 판별(CP-11), 방문지별 동시 처리 ----
        done = {"n": 0}
        total = len(visit_ids)

        def work(visit_id: str) -> None:
            try:
                self._match_visit(trip_id, visit_id)
            except Exception as e:  # 방문지 단위 실패 격리 (AC-16)
                log.exception("visit match failed")
                with SessionLocal() as db2:
                    v = db2.get(Visit, visit_id)
                    v.status, v.note = VisitStatus.NEEDS_SELECTION.value, f"분석 중 오류: {e}"[:300]
                    db2.commit()
            with self._progress_lock:
                done["n"] += 1
                k = done["n"]
            self._update(job_id, "match", k / max(total, 1), {"match": {"done": k, "total": total}})

        if total:
            with ThreadPoolExecutor(max_workers=MATCH_WORKERS) as pool:
                list(pool.map(work, visit_ids))

        # ---- 4. 위치 없는 사진 추천(CP-12) → 마무리 ----
        with SessionLocal() as db:
            trip = db.get(Trip, trip_id)
            visits = self.repo.visits(db, trip_id)
            spans = [VisitSpan(v.id, self._visit_label(db, v), v.start_at, v.end_at) for v in visits]
            rep_images = {v.id: self.media.read_vlm_image(trip_id, v.rep_photo_id) for v in visits if v.rep_photo_id}
            rep_images = {k: img for k, img in rep_images.items() if img}
            pending = [p for p in trip.photos if p.visit_id is None]
            for i, p in enumerate(pending):
                s = self.resolver.resolve(p.taken_at, spans, self.media.read_vlm_image(trip_id, p.id), rep_images)
                p.suggested_visit_id, p.suggest_reason, p.assign_state = s.visit_id, s.reason, "pending"
                self._update(job_id, "finalize", (i + 1) / (len(pending) + 1))
            trip.status = "review"
            self.repo.refresh_trip_status(trip)
            db.commit()
            counts = {s.value: sum(1 for v in visits if v.status == s.value) for s in VisitStatus}
            self._update(job_id, "finalize", 1.0, {"result": {"statuses": counts, "untagged": len(pending)}})

    def _visit_label(self, db, v: Visit) -> str:
        rec = self.cache.resolve(db, v.place_id or v.ai_place_id, v.center_lat, v.center_lng)
        return rec.name if rec and rec.name else f"방문지 {v.order}"

    def _match_visit(self, trip_id: str, visit_id: str) -> None:
        with SessionLocal() as db:
            v = db.get(Visit, visit_id)
            if v.center_lat is None:  # 위치 있는 사진이 없는 방문지 → 직접 검색 (UC-01 5b)
                v.status, v.note = VisitStatus.NEEDS_SELECTION.value, "위치 정보가 없어 직접 장소를 골라 주세요"
                db.commit()
                return
            try:
                cands, radius = self.finder.find(db, v.center_lat, v.center_lng)
            except CandidateLookupError:
                v.status, v.note = VisitStatus.NEEDS_SELECTION.value, "장소 데이터를 불러오지 못했어요 (2회 재시도 실패)"
                db.commit()
                return
            v.candidates = [{"place_id": c.place_id, "distance_m": round(c.distance_m)} for c in cands]
            v.search_radius_m = radius
            if not cands:
                v.status, v.note = VisitStatus.NEEDS_SELECTION.value, f"반경 {radius}m 안에 공식 데이터 후보가 없어요"
                db.commit()
                return
            image = self.media.read_vlm_image(trip_id, v.rep_photo_id) if v.rep_photo_id else None
            if image is None:
                v.status, v.note = VisitStatus.NEEDS_SELECTION.value, "대표 사진을 읽지 못했어요"
                db.commit()
                return
            # VLM 입력 (AIR-01): 카카오 후보는 이름·유형·거리만
            vlm_cands = []
            for c in cands:
                d = {"place_id": c.place_id, "name": c.record.name, "type": c.record.type, "distance_m": round(c.distance_m)}
                if c.record.source != "kakao":
                    d["overview"] = c.record.overview
                vlm_cands.append(d)
            try:
                answer, error = self.matcher.ask(image, vlm_cands)
            except AIError as e:
                answer, error = None, str(e)
            for log_row in self.matcher.apply(v, answer, error):
                db.add(log_row)
            db.commit()
