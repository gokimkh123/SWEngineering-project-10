"""찰칵부산 API 서버 진입점 (FastAPI).

실행: uvicorn app.main:app --reload   (backend/ 에서)
- REST API는 /api/v1 아래 (설계서 3.2)
- frontend/dist가 있으면 같은 서버에서 정적 파일도 제공한다 (설계서 2.5의 웹 서버 역할을 단순화)
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from app.adapters.cp18_place_data import SOURCE_LICENSES, SOURCE_NAMES, place_adapter
from app.adapters.cp19_ai_gateway import ai_gateway
from app import demo
from app.api import cp02_trip_api, cp03_visit_api, cp04_story_api
from app.api.deps import device_token
from app.components.cp11_matcher import AUTO_THRESHOLD, CHECK_THRESHOLD
from app.components.cp17_media_store import media_store
from app.config import BASE_DIR, settings
from app.models import init_db
from app.services import place_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
DEMO_DIR = demo.DEMO_DIR


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    media_store.cleanup_orphans()  # 비정상 종료로 남은 원본 정리 (QA-04)
    yield


app = FastAPI(title="찰칵부산 API", version="0.1.0-prototype", lifespan=lifespan,
              description="부산 여행 사진 → 방문지·동선·출처 있는 여행기 (Team 10 프로토타입)")

meta = APIRouter(tags=["Meta"])


@meta.get("/health")
def health():
    return {"ok": True}


@meta.get("/meta")
def service_meta():
    """현재 동작 모드, 데이터 출처·이용조건 (REQ-06, REQ-07), 캐시·AI 호출 기록 (NFR-08, AIR-07)."""
    return {
        "place_data": place_adapter.modes(),
        "ai": ai_gateway.info(),
        "thresholds": {"auto": AUTO_THRESHOLD, "check": CHECK_THRESHOLD},
        "limits": {"max_photos": settings.max_photos, "max_photo_mb": settings.max_photo_bytes // (1024 * 1024)},
        "sources": [{"key": k, "name": SOURCE_NAMES[k], "license": SOURCE_LICENSES[k]} for k in SOURCE_NAMES],
        "cache": place_cache.stats(),
        "api_calls": {"ok": dict(place_adapter.stats.counts), "failed": dict(place_adapter.stats.failures)},
        "queue": "rq" if settings.redis_url else "in-process",
        "database": "postgresql" if settings.database_url.startswith("postgres") else "sqlite",
    }


@meta.get("/demo/photos")
def demo_photos():
    """시연용 샘플 사진 목록 (scripts/make_demo_photos.py로 생성). 브라우저가 받아서 일반 업로드로 올린다."""
    if not DEMO_DIR.exists():
        return {"photos": []}
    return {"photos": sorted(p.name for p in DEMO_DIR.glob("*.jpg"))}


@meta.post("/demo/seed", status_code=201)
def demo_seed(owner: str = Depends(device_token)):
    """완성된 시연 여행 한 번에 만들기 (발표용). 실제 파이프라인을 돌리고 확인 단계만 AI 추천대로 처리한다."""
    try:
        return demo.seed_demo_trip(owner)
    except FileNotFoundError as e:
        raise HTTPException(409, str(e)) from e


@meta.get("/demo/photos/{name}")
def demo_photo(name: str):
    path = (DEMO_DIR / name).resolve()
    if path.parent != DEMO_DIR.resolve() or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg")


for r in (meta, cp02_trip_api.router, cp03_visit_api.router, cp04_story_api.router):
    app.include_router(r, prefix="/api/v1")


# ---- 프론트엔드 정적 파일 (빌드돼 있을 때만) ----
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return Response(status_code=404)
        f = (FRONTEND_DIST / path).resolve()
        if path and f.is_file() and FRONTEND_DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
