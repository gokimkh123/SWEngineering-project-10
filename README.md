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
python3 demo.py --photos real         # 실제 사진 9장으로 시연 (저장소 루트에 KakaoTalk_*.jpg 원본 필요, 커밋 안 됨)
python3 demo.py --photos synthetic    # 합성 사진 24장으로 시연 (원본이 없으면 기본값)
```

## 테스트

```bash
cd backend
.venv/bin/python -m pytest            # Windows: .venv\Scripts\python -m pytest
```
