"""테스트 공통 설정: 임시 데이터 폴더, 모의 AI 지연 없음, 합성 사진 세트."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="chalkak-test-")
os.environ["CHALKAK_NO_DOTENV"] = "1"  # 개발자의 실제 키(.env)를 테스트에 쓰지 않음
os.environ["DATA_DIR"] = _TMP
os.environ.pop("FAULT_INJECT", None)
os.environ["FAKE_AI_LATENCY"] = "0"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("REDIS_URL", None)
for k in ("TOUR_API_KEY", "BUSAN_API_KEY", "KAKAO_REST_KEY"):
    os.environ.pop(k, None)
os.environ["VLM_PROVIDER"] = "fake"
os.environ["LLM_PROVIDER"] = "fake"

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def demo_dir() -> Path:
    import make_demo_photos

    out = Path(_TMP) / "demo_photos"
    make_demo_photos.main(out)
    return out


@pytest.fixture(scope="session")
def demo_labels(demo_dir):
    import json

    return json.loads((demo_dir / "labels.json").read_text(encoding="utf-8"))
