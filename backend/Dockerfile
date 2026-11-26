# 찰칵부산 API·워커 이미지 (설계서 2.5 배포 구조의 api / worker 컨테이너)
FROM python:3.12.16-slim-trixie
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 DATA_DIR=/data
# 공유 카드(CP-06) 한글 글꼴
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum && rm -rf /var/lib/apt/lists/*
# root가 아닌 사용자로 실행. /data(공유 볼륨)는 이 사용자 소유로 만들어 둔다(빈 볼륨이 이 소유권을 이어받음)
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data && chown app:app /data
WORKDIR /srv/backend
COPY requirements.txt requirements-deploy.txt constraints.txt ./
RUN pip install -c constraints.txt -r requirements.txt -r requirements-deploy.txt
COPY app ./app
COPY scripts ./scripts
USER app
EXPOSE 8000
# 시연용 '샘플 사진으로 체험'에는 그림으로 만든 합성 사진만 쓴다(실제 사람 사진을 공개 서버에 두지 않음)
# 접속 기록(쿼리의 기기 토큰 포함)은 남기지 않고, 요청 기록은 web(nginx)이 쿼리 없이 남긴다
CMD ["sh", "-c", "[ -f \"$DATA_DIR/demo_photos/labels.json\" ] || python scripts/make_demo_photos.py \"$DATA_DIR/demo_photos\"; exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log --timeout-graceful-shutdown 10"]
