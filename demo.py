#!/usr/bin/env python3
"""찰칵부산 시연 실행기 — 명령 하나로 설치·빌드·서버 실행·브라우저 열기.

사용:
  python demo.py            # 처음이면 설치·빌드까지 하고 http://localhost:8000 을 연다
  python demo.py --reset    # 이전 시연 기록(DB·썸네일)을 지우고 깨끗하게 시작
  python demo.py --lan      # 같은 Wi-Fi의 휴대폰에서도 접속 가능하게 (0.0.0.0)
  python demo.py --port 8080 --no-browser
  python demo.py --photos real       # 시연 사진을 실제 사진 9장으로 (촬영 시각·위치는 임의 각색)
  python demo.py --photos synthetic  # 시연 사진을 합성 사진 24장으로

필요: Python 3.10+, (처음 한 번 화면 빌드용) Node.js 18+
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
VAR = BACKEND / "var"
VENV = BACKEND / ".venv"
PY = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def step(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def run(cmd: list, cwd: Path) -> None:
    subprocess.run([str(c) for c in cmd], cwd=cwd, check=True)


def ensure_backend() -> None:
    if not PY.exists():
        step("Python 가상환경 만들기 (backend/.venv)")
        run([sys.executable, "-m", "venv", VENV], ROOT)
    req = (BACKEND / "requirements.txt").read_bytes()
    marker = VENV / ".deps-ok"
    digest = hashlib.sha256(req).hexdigest()
    if not marker.exists() or marker.read_text() != digest:
        step("백엔드 패키지 설치 (처음 한 번, 1~3분)")
        run([PY, "-m", "pip", "install", "-q", "--disable-pip-version-check", "-r", "requirements.txt"], BACKEND)
        marker.write_text(digest)


def ensure_demo_photos(which: str | None) -> None:
    """시연 사진 세트 준비. 기본은 있는 세트를 그대로 쓰고, 없으면 실제 사진 → 합성 사진 순으로 만든다."""
    if which is None and (VAR / "demo_photos" / "labels.json").exists():
        return
    if which in (None, "real"):
        check = subprocess.run([str(PY), "scripts/import_demo_photos.py", "--check"], cwd=BACKEND, capture_output=True)
        if check.returncode == 0:
            step("실제 사진으로 시연 세트 만들기 (촬영 시각·위치는 부산 여행처럼 임의로 정한 값)")
            run([PY, "scripts/import_demo_photos.py"], BACKEND)
            return
        if which == "real":
            sys.exit("실제 사진 원본이 없어요: " + check.stderr.decode(errors="replace").strip())
    step("합성 시연 사진 24장 만들기")
    run([PY, "scripts/make_demo_photos.py"], BACKEND)


def ensure_frontend() -> None:
    dist = FRONTEND / "dist" / "index.html"
    sources = [p for p in (FRONTEND / "src").rglob("*") if p.is_file()] + [FRONTEND / "index.html"]
    stale = not dist.exists() or max(p.stat().st_mtime for p in sources) > dist.stat().st_mtime
    if not stale:
        return
    npm = shutil.which("npm")
    if not npm:
        if dist.exists():
            print("   (npm이 없어 기존 빌드로 실행합니다)")
            return
        sys.exit("화면 빌드에 Node.js가 필요해요: https://nodejs.org 설치 후 다시 실행해 주세요.")
    if not (FRONTEND / "node_modules").exists():
        step("화면 패키지 설치 (처음 한 번)")
        run([npm, "install", "--no-audit", "--no-fund"], FRONTEND)
    step("화면 빌드 (frontend/dist)")
    run([npm, "run", "build"], FRONTEND)


def reset() -> None:
    step("이전 시연 기록 지우기 (DB·썸네일·공유 카드)")
    for name in ("chalkak.db", "chalkak.db-wal", "chalkak.db-shm"):
        (VAR / name).unlink(missing_ok=True)
    for d in ("thumbs", "originals", "cards"):
        shutil.rmtree(VAR / d, ignore_errors=True)


def lan_ips() -> list[str]:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return [ip]
    except OSError:
        return []


def main() -> None:
    ap = argparse.ArgumentParser(description="찰칵부산 시연 실행기")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--lan", action="store_true", help="같은 네트워크의 휴대폰에서도 접속")
    ap.add_argument("--reset", action="store_true", help="이전 시연 기록 지우기")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--photos", choices=["real", "synthetic"],
                    help="시연 사진 세트를 다시 만든다 (real: 저장소 루트의 실제 사진 9장, synthetic: 합성 사진 24장)")
    args = ap.parse_args()
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 이상이 필요해요.")

    ensure_backend()
    ensure_demo_photos(args.photos)
    ensure_frontend()
    if args.reset:
        reset()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    url = f"http://localhost:{args.port}"
    step(f"서버 시작 → {url}  (끝내려면 Ctrl+C)")
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([str(PY), "-m", "uvicorn", "app.main:app", "--host", host, "--port", str(args.port),
                             "--log-level", "warning"], cwd=BACKEND, env=env)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{url}/api/v1/health", timeout=1)
                break
            except OSError:
                if proc.poll() is not None:
                    sys.exit("서버를 시작하지 못했어요. 포트가 이미 쓰이고 있으면 --port 8080 처럼 바꿔 보세요.")
                time.sleep(0.5)
        print(f"\n   찰칵부산 준비 완료: {url}")
        if args.lan:
            for ip in lan_ips():
                print(f"   휴대폰(같은 Wi-Fi): http://{ip}:{args.port}")
        print("   시연: 홈 → '새 여행기' → '샘플 사진으로 체험' → 동의 → 분석 시작")
        print("         또는 홈 → '완성된 시연 여행 바로 보기'")
        if not args.no_browser:
            webbrowser.open(url)
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("\n서버를 종료했어요.")


if __name__ == "__main__":
    main()
