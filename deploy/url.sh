#!/usr/bin/env bash
# 지금 공개 주소(Cloudflare Quick Tunnel, https://….trycloudflare.com)를 보여 준다.
# 터널 컨테이너를 다시 시작하거나 PC를 껐다 켜면 주소가 새로 바뀐다.
set -uo pipefail
cd "$(dirname "$0")/.."
for _ in $(seq 1 45); do
  url=$(docker compose logs tunnel 2>/dev/null | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)
  if [ -n "$url" ]; then
    echo "$url"
    exit 0
  fi
  sleep 2
done
echo "공개 주소를 찾지 못했어요. 확인: docker compose logs tunnel" >&2
exit 1
