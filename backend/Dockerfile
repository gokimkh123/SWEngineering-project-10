# 찰칵부산 API·워커 이미지 (설계서 2.5 배포 구조의 api / worker 컨테이너)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
# 공유 카드(CP-06) 한글 글꼴
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/backend
COPY requirements.txt requirements-optional.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-optional.txt
COPY app ./app
COPY scripts ./scripts
EXPOSE 8000
# 시연용 합성 사진을 데이터 볼륨에 만들고 서버 시작
CMD ["sh", "-c", "[ -d $DATA_DIR/demo_photos ] || python scripts/make_demo_photos.py $DATA_DIR/demo_photos; uvicorn app.main:app --host 0.0.0.0 --port 8000"]
