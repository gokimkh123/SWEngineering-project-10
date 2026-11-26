#!/usr/bin/env bash
# 찰칵부산 공개 서버를 이 PC(Docker Desktop + NVIDIA GPU)에서 한 번에 띄운다.
#   1) 비밀값 생성(deploy/chalkak.env, 처음 한 번)  2) VLM 서버 → 모델 받기  3) 나머지 빌드·실행  4) 공개 주소 출력
# 다시 실행해도 된다(이미 받은 모델·데이터는 그대로). 공개 주소는 터널을 다시 시작할 때만 바뀐다.
set -euo pipefail
cd "$(dirname "$0")/.."
ENV_FILE=deploy/chalkak.env

docker info >/dev/null 2>&1 || { echo "Docker Desktop을 켠 뒤 다시 실행해 주세요." >&2; exit 1; }

if [ ! -f "$ENV_FILE" ]; then
  echo "==> 비밀값 만들기 ($ENV_FILE)"
  python3 - "$ENV_FILE" <<'PY'
import secrets, sys
from pathlib import Path
pg, rd = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
text = Path("deploy/chalkak.env.example").read_text(encoding="utf-8")
text = (text.replace("POSTGRES_PASSWORD=__생성됨__", f"POSTGRES_PASSWORD={pg}")
            .replace("REDIS_PASSWORD=__생성됨__", f"REDIS_PASSWORD={rd}")
            .replace("chalkak:__생성됨__@postgres", f"chalkak:{pg}@postgres")
            .replace("redis://:__생성됨__@redis", f"redis://:{rd}@redis"))
out = Path(sys.argv[1])
out.write_text(text, encoding="utf-8")
out.chmod(0o600)
PY
fi

MODEL=$(grep -E '^VLM_MODEL=' "$ENV_FILE" | cut -d= -f2 | tr -d '[:space:]')
echo "==> VLM 서버 시작, 모델 받기: $MODEL (처음 한 번 수 GB)"
docker compose up -d vlm
until docker compose exec -T vlm ollama list >/dev/null 2>&1; do sleep 2; done
docker compose exec -T vlm ollama pull "$MODEL"

echo "==> 빌드·실행 (web · api · worker · redis · postgres · tunnel)"
docker compose up -d --build

echo "==> 공개 주소"
deploy/url.sh
