"""CP-17 Media Store (Data 계층).

책임: 원본 사진 임시 저장과 자동 삭제(작업 종료·주기 정리), EXIF 제거 썸네일 보관 (DR-04, DR-08, QA-04).
저장 위치: 공유 볼륨(설계서 2.5). 프로토타입은 DATA_DIR 아래 디렉터리를 쓴다.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from app.config import settings


class MediaStore:
    def __init__(self, root: Path | None = None) -> None:
        root = root or settings.data_dir
        self.originals = root / "originals"  # 임시 — 분석 후 삭제
        self.thumbs = root / "thumbs"  # 보관 — EXIF 없는 썸네일만
        self.cards = root / "cards"  # 공유 카드 이미지
        for d in (self.originals, self.thumbs, self.cards):
            d.mkdir(parents=True, exist_ok=True)

    # ---- 원본 (임시) ----
    def _orig_dir(self, trip_id: str) -> Path:
        return self.originals / trip_id

    def save_original(self, trip_id: str, photo_id: str, data: bytes) -> None:
        d = self._orig_dir(trip_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / photo_id).write_bytes(data)

    def read_original(self, trip_id: str, photo_id: str) -> bytes | None:
        p = self._orig_dir(trip_id) / photo_id
        return p.read_bytes() if p.exists() else None

    def save_vlm_image(self, trip_id: str, photo_id: str, data: bytes) -> None:
        d = self._orig_dir(trip_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{photo_id}.vlm.jpg").write_bytes(data)

    def read_vlm_image(self, trip_id: str, photo_id: str) -> bytes | None:
        p = self._orig_dir(trip_id) / f"{photo_id}.vlm.jpg"
        return p.read_bytes() if p.exists() else None

    def delete_originals(self, trip_id: str) -> int:
        """작업이 끝나면(성공·실패 무관) 원본과 VLM용 축소본을 모두 지운다."""
        d = self._orig_dir(trip_id)
        if not d.exists():
            return 0
        n = sum(1 for _ in d.iterdir())
        shutil.rmtree(d, ignore_errors=True)
        return n

    def remaining_originals(self, trip_id: str) -> int:
        d = self._orig_dir(trip_id)
        return sum(1 for _ in d.iterdir()) if d.exists() else 0

    def cleanup_orphans(self, active_trip_ids: set[str] | None = None) -> int:
        """주기 정리: 진행 중인 작업이 아닌데 오래 남은 원본을 지운다 (워커 비정상 종료 대비)."""
        limit = time.time() - settings.orphan_original_minutes * 60
        removed = 0
        for d in self.originals.iterdir():
            if not d.is_dir() or (active_trip_ids and d.name in active_trip_ids):
                continue
            if d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed

    # ---- 썸네일 (보관) ----
    def save_thumb(self, photo_id: str, data: bytes) -> None:
        (self.thumbs / f"{photo_id}.jpg").write_bytes(data)

    def thumb_path(self, photo_id: str) -> Path:
        return self.thumbs / f"{photo_id}.jpg"

    def read_thumb(self, photo_id: str) -> bytes | None:
        p = self.thumb_path(photo_id)
        return p.read_bytes() if p.exists() else None

    def delete_thumbs(self, photo_ids: list[str]) -> None:
        for pid in photo_ids:
            self.thumb_path(pid).unlink(missing_ok=True)

    # ---- 공유 카드 ----
    def card_path(self, story_id: str) -> Path:
        return self.cards / f"{story_id}.png"

    def delete_card(self, story_id: str) -> None:
        self.card_path(story_id).unlink(missing_ok=True)

    def delete_trip_media(self, trip_id: str, photo_ids: list[str], story_ids: list[str]) -> None:
        """여행 삭제 시 관련 파일 전부 삭제 (NFR-04)."""
        self.delete_originals(trip_id)
        self.delete_thumbs(photo_ids)
        for sid in story_ids:
            self.delete_card(sid)


media_store = MediaStore()
