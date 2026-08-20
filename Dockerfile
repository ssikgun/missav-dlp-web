FROM python:3.10-slim

# 1. uv 바이너리 복사
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 2. 필수 패키지 설치
RUN apt-get update && \
    apt-get install -y ffmpeg curl bash && \
    rm -rf /var/lib/apt/lists/*

# 3. SpoofDPI 설치
RUN curl -fsSL https://raw.githubusercontent.com/xvzc/SpoofDPI/main/install.sh | bash -s linux-amd64

WORKDIR /app

# 4. 파이썬 패키지 고속 설치
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Teddy custom: 런타임 핵심 의존성 import를 빌드 단계에서 검증
RUN python -c "import typing_extensions; import curl_cffi; import yt_dlp; import flask; print('dependency smoke test: OK')"

# 5. 애플리케이션 복사
COPY . .

# Teddy custom: 원본 index.html은 건드리지 않고 커스텀 UI 레이어만 빌드 시 삽입
RUN sed -i 's#</body>#<script src="/static/teddy-speed.js"></script><script src="/static/teddy-reliability.js"></script></body>#' templates/index.html

# 6. 폴더 생성 및 포트 노출
RUN mkdir -p /downloads
EXPOSE 5000

# 7. Teddy 안정성 레이어를 적용한 엔트리포인트 실행
CMD ["python", "teddy_entrypoint.py"]
