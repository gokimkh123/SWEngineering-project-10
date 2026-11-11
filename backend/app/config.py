"""환경 설정 (설계서 2.5 배포 구조).

모든 외부 키는 서버 환경변수로만 받는다 (NFR-07, AC-15). 키가 없으면 샘플 데이터·모의 AI로 동작해
외부 서비스 없이도 전체 흐름을 시연·테스트할 수 있다 (QA-08).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def _load_dotenv(path: Path) -> None:
    """저장소 루트의 .env를 읽어 환경변수로 넣는다 (이미 설정된 값이 우선). 테스트는 CHALKAK_NO_DOTENV=1로 끈다."""
    if os.environ.get("CHALKAK_NO_DOTENV") == "1" or not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


_load_dotenv(BASE_DIR.parent / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(BASE_DIR / "var"))))
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL"))

    # CP-18 장소 데이터: 키가 있으면 실제 API, 없으면 샘플 데이터
    tour_api_key: str = field(default_factory=lambda: _env("TOUR_API_KEY"))
    busan_api_key: str = field(default_factory=lambda: _env("BUSAN_API_KEY"))
    kakao_rest_key: str = field(default_factory=lambda: _env("KAKAO_REST_KEY"))

    # CP-19 AI Gateway
    vlm_provider: str = field(default_factory=lambda: _env("VLM_PROVIDER", "fake"))  # fake | ollama
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    vlm_model: str = field(default_factory=lambda: _env("VLM_MODEL", "qwen2.5vl:7b"))
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "fake"))  # fake | anthropic | gemini
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-haiku-5-5"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-2.5-flash"))
    # 모의 AI 응답 지연(초). 시연 때 진행률 화면(A3)이 보이도록 기본 1.2초(분석 약 5초), 테스트에서는 0
    fake_ai_latency: float = field(default_factory=lambda: _env_float("FAKE_AI_LATENCY", 1.2))

    # 업로드 제한 (FR-01)
    max_photos: int = 30
    max_photo_bytes: int = 20 * 1024 * 1024

    # 원본 사진 주기 정리 기준(분) — 작업이 비정상 종료돼도 남지 않게 (QA-04)
    orphan_original_minutes: int = 30

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'chalkak.db'}"

    @property
    def place_mode(self) -> str:
        return "real" if (self.tour_api_key or self.kakao_rest_key or self.busan_api_key) else "sample"


settings = Settings()
