# 찰칵부산 — 실행 방법

필요: Python 3.10 이상, Node.js 18 이상 (처음 실행할 때 화면 빌드용), Git

처음 실행하면 패키지 설치·시연 사진 생성·화면 빌드를 자동으로 하고 서버를 띄운다. 끝낼 때는 `Ctrl+C`.

## Windows (PowerShell)

```powershell
git clone https://github.com/gokimkh123/SWEngineering-project-10.git
cd SWEngineering-project-10
py demo.py                 # 브라우저가 http://localhost:8000 으로 열림
py demo.py --reset         # 이전 시연 기록 지우고 시작 (발표 직전)
py demo.py --port 8080     # 8000번 포트가 쓰이고 있을 때
```

## Linux

```bash
git clone https://github.com/gokimkh123/SWEngineering-project-10.git
cd SWEngineering-project-10
python3 demo.py            # 브라우저가 http://localhost:8000 으로 열림
python3 demo.py --reset    # 이전 시연 기록 지우고 시작 (발표 직전)
python3 demo.py --port 8080
```

- `venv` 오류가 나면 (Ubuntu): `sudo apt install python3-venv`

## WSL

```bash
git clone https://github.com/gokimkh123/SWEngineering-project-10.git
cd SWEngineering-project-10
python3 demo.py --no-browser          # Windows 브라우저에서 http://localhost:8000 직접 열기
python3 demo.py --reset --no-browser
python3 demo.py --port 8080 --no-browser
```

- `venv` 오류가 나면: `sudo apt install python3-venv`

## 공통 옵션

```bash
python3 demo.py --lan                 # 같은 Wi-Fi의 휴대폰에서 접속 (표시되는 주소로)
python3 demo.py --photos real         # 실제 사진 9장으로 시연 (photos/ 폴더에 KakaoTalk_*.jpg 원본 필요, 커밋 안 됨)
python3 demo.py --photos synthetic    # 합성 사진 24장으로 시연 (원본이 없으면 기본값)
```

## 공개 서버 (Docker + 실제 AI + Cloudflare 무료 터널)

필요: Docker Desktop (WSL 연동 켬), NVIDIA GPU. 이 PC에서 실행하고 `https://….trycloudflare.com` 주소로 공개된다.

```bash
deploy/setup.sh                       # 처음 한 번: 비밀값 생성 → Qwen 모델 받기 → 빌드·실행 → 공개 주소 출력
deploy/url.sh                         # 지금 공개 주소 (터널·PC를 다시 켜면 주소가 바뀜)
docker compose ps                     # 상태
docker compose logs -f worker         # 분석 기록
docker compose down                   # 끄기 (모델·데이터는 남음) / 다시 켜기: docker compose up -d
docker compose up -d --build api worker   # deploy/chalkak.env 를 고친 뒤 (공개 주소 유지)
```

- 설정·비밀값: `deploy/chalkak.env` (저장소에 안 올라감). 모델 바꾸기: `VLM_MODEL=qwen3.5:9b` 후 `docker compose exec vlm ollama pull qwen3.5:9b`
- 장소 API 키(`TOUR_API_KEY`·`BUSAN_API_KEY`·`KAKAO_REST_KEY`)를 넣으면 샘플 장소 40곳 대신 실제 관광 데이터로 후보를 찾음
- 모델 비교 시험: `docker compose run --rm --no-deps -v "$PWD/deploy/bench:/bench:ro" api python scripts/vlm_bench.py /bench/manifest.json qwen3.5:2b qwen3.5:4b qwen3.5:9b`

## 테스트

```bash
cd backend
.venv/bin/python -m pytest            # Windows: .venv\Scripts\python -m pytest
```
