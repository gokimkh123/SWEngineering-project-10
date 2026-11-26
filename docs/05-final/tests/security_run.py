"""보안 점검 (NFR-07 · 공개 서버) — 공개 주소로 외부 사용자와 같은 경로에서 확인. 결과: JSON."""
import io
import json
import re
import secrets
import sys
import time

import httpx
from PIL import Image

U = sys.argv[1].rstrip("/")
OUT = sys.argv[2]
checks = []


def add(item, expected, actual, ok):
    checks.append({"item": item, "expected": expected, "actual": actual, "pass": bool(ok)})
    print(("PASS " if ok else "FAIL ") + item + " → " + actual)


c = httpx.Client(timeout=60)
A = {"X-Device-Token": "sec-" + secrets.token_hex(12)}
Bh = {"X-Device-Token": "sec-" + secrets.token_hex(12)}

codes = {p: c.get(U + p).status_code for p in ("/api/v1/docs", "/api/v1/openapi.json", "/api/v1/redoc")}
add("API 문서·스키마 비공개", "404", ", ".join(f"{k.split('/')[-1]} {v}" for k, v in codes.items()), all(v == 404 for v in codes.values()))
r = c.post(U + "/api/v1/demo/seed", headers=A)
add("시연용 데이터 생성 주소 차단", "404", str(r.status_code), r.status_code == 404)
r = c.get(U + "/api/v1/trips")
add("기기 토큰 없는 요청 거부", "401", str(r.status_code), r.status_code == 401)
outs = []
for path in ("/api/v1/photos/..%2F..%2F..%2Fetc%2Fpasswd/thumb", "/api/v1/photos/%2e%2e/%2e%2e/etc/passwd/thumb"):
    r = c.get(U + path, params={"t": A["X-Device-Token"]})
    outs.append((r.status_code, r.headers.get("content-type", "").split(";")[0], "root:" in r.text))
add("경로 조작(../)으로 서버 파일 접근 불가", "파일 내용 노출 없음 (앱 화면 또는 404)",
    " / ".join(f"{s} {ct}" for s, ct, _ in outs) + " · 파일 내용 노출 0건", not any(x[2] for x in outs))

time.sleep(2)
t = c.post(U + "/api/v1/trips", json={"title": "보안 점검"}, headers=A).json()["id"]
try:
    r = c.get(U + f"/api/v1/trips/{t}", headers=Bh)
    add("다른 기기의 여행 접근 차단", "404", str(r.status_code), r.status_code == 404)
    r = c.post(U + f"/api/v1/trips/{t}/photos", headers=A, files=[("files", ("fake.jpg", b"not an image at all" * 10, "image/jpeg"))]).json()
    add("이미지로 위장한 파일 거부", "접수 0장", f"접수 {len(r['accepted'])}장 · 사유 '{r['rejected'][0]['reason'] if r['rejected'] else '-'}'", not r["accepted"] and r["rejected"])
    big = b"\xff\xd8\xff" + b"\0" * (46 * 1024 * 1024)
    r = c.post(U + f"/api/v1/trips/{t}/photos", headers=A, files=[("files", ("big.jpg", big, "image/jpeg"))])
    add("요청당 45MB 초과 업로드 차단", "413", str(r.status_code), r.status_code == 413)
finally:
    c.delete(U + f"/api/v1/trips/{t}", headers=A)

time.sleep(3)
import asyncio  # noqa: E402


async def _burst():
    async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=60)) as ac:
        return [r.status_code for r in await asyncio.gather(*[ac.get(U + "/api/v1/meta") for _ in range(120)])]
codes = asyncio.run(_burst())
n429 = codes.count(429)
add("요청 폭주 제한 (IP당 초당 15회·순간 40회)", "한도 초과분 429", f"동시 120회 요청 → 200 {codes.count(200)}회 · 429 {n429}회", n429 > 0 and codes.count(200) >= 40)
time.sleep(5)

r = c.get(U + "/")
h = {k.lower(): v for k, v in r.headers.items()}
want = ["content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy", "strict-transport-security", "permissions-policy"]
have = [k for k in want if k in h]
add("보안 헤더 (CSP·HSTS·X-Frame-Options 등)", "6종", f"{len(have)}/6종 · X-Frame-Options {h.get('x-frame-options')}", len(have) == 6)
srv = h.get("server", "")
add("서버 버전 비노출", "버전 숫자 없음", f"Server: {srv}", not re.search(r"\d", srv))

js = re.findall(r'src="(/assets/[^"]+\.js)"', r.text)
leaks = []
for p in js:
    body = c.get(U + p).text
    for pat in (r"serviceKey=", r"KakaoAK\s+[0-9a-f]{20,}", r"sk-ant-[A-Za-z0-9]", r"AIza[0-9A-Za-z_-]{30,}", r"TOUR_API_KEY", r"POSTGRES_PASSWORD", r"REDIS_PASSWORD"):
        if re.search(pat, body):
            leaks.append(pat)
add("클라이언트 JS에 서버 키 없음", "0건", f"번들 {len(js)}개 검사 · 발견 {len(leaks)}건", not leaks)

json.dump({"run_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": checks}, open(OUT, "w"), ensure_ascii=False, indent=1)
print("PASS", sum(x["pass"] for x in checks), "/", len(checks))
