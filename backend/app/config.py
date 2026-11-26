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


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
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
    # VLM 한 번 호출의 시간 제한(초). 모델을 GPU에 처음 올리는 시간까지 포함해야 한다
    vlm_timeout: float = field(default_factory=lambda: _env_float("VLM_TIMEOUT", 180))
    # 방문지별 동시 VLM 호출 수 (QA-01). 실제 VLM은 GPU 하나를 나눠 쓰므로 2 정도가 알맞다
    match_workers: int = field(default_factory=lambda: max(1, _env_int("MATCH_WORKERS", 4)))
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "fake"))  # fake | ollama | anthropic | gemini
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL"))  # ollama일 때, 비우면 VLM과 같은 모델(GPU에 하나만 올림)
    llm_timeout: float = field(default_factory=lambda: _env_float("LLM_TIMEOUT", 240))
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

    # 공개 서비스 모드 (인터넷에 공개할 때, deploy/chalkak.env): API 문서·즉석 시연 여행을 끄고 아래 한도를 쓴다
    public_mode: bool = field(default_factory=lambda: _env("PUBLIC_MODE") == "1")
    # 만든 지 이 일수가 지난 여행은 썸네일·방문지·여행기까지 자동 삭제 (0이면 끔)
    retention_days: float = field(default_factory=lambda: _env_float("RETENTION_DAYS", 0))
    # 동시에 대기·실행 중인 분석·여행기 작업 수 상한(서버 전체) — GPU 작업이 무한히 쌓이지 않게
    max_active_jobs: int = field(default_factory=lambda: _env_int("MAX_ACTIVE_JOBS", 20))
    # 기기 토큰 하나가 하루에 만들 수 있는 여행 수
    max_trips_per_day: int = field(default_factory=lambda: _env_int("MAX_TRIPS_PER_DAY", 20))

    def __post_init__(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.database_url:
            self.database_url = f"sqlite:///{self.data_dir / 'chalkak.db'}"

    @property
    def demo_seed(self) -> bool:
        """'완성된 시연 여행 바로 보기'(분석 전체를 요청 안에서 돌림) — 공개 모드에서는 끈다."""
        return _env("DEMO_SEED", "0" if self.public_mode else "1") == "1"

    @property
    def place_mode(self) -> str:
        return "real" if (self.tour_api_key or self.kakao_rest_key or self.busan_api_key) else "sample"


settings = Settings()
