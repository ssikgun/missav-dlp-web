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
RUN python -m py_compile teddy_entrypoint.py teddy_network.py teddy_logging.py teddy_bootstrap.py teddy_patch_index.py teddy_patch_logs.py && \
    python -c "import teddy_network as n; assert n.is_recoverable_failure('HTTP 403'); assert n.is_recoverable_failure('operation timed out'); assert n.is_recoverable_failure('connection reset by peer'); assert not n.is_recoverable_failure('HTTP 404'); assert not n.is_recoverable_failure('HTTP 401'); print('automatic VPN recovery boundary smoke test: OK')"

# Teddy custom: 범용 브랜딩 + 안정적인 keyed task UI + 로그 페이지를 빌드 시 적용
# 패치 대상이 upstream 변경으로 달라지면 패치 스크립트가 빌드를 실패시킨다.
RUN python teddy_patch_index.py && \
    python teddy_patch_logs.py && \
    sed -i 's#</head>#<link rel="stylesheet" href="/static/teddy-theme.css"><link rel="stylesheet" href="/static/teddy-network.css"><link rel="stylesheet" href="/static/teddy-logs.css"></head>#' templates/index.html && \
    sed -i 's#</body>#<script src="/static/teddy-reliability.js"></script><script src="/static/teddy-theme.js"></script><script src="/static/teddy-network.js"></script><script src="/static/teddy-logs.js"></script></body>#' templates/index.html && \
    grep -q '<title>Downloader</title>' templates/index.html && \
    grep -q 'teddyEffectiveSpeed' templates/index.html && \
    grep -q '남은 시간 약' templates/index.html && \
    grep -q 'Ⅱ 일시정지' templates/index.html && \
    grep -q 'teddy-network.js' templates/index.html && \
    grep -q '자동 복구' templates/teddy-network.js && \
    grep -q 'auto_recover' teddy_network.py && \
    grep -q '_fetch_segment_with_network_recovery' teddy_bootstrap.py && \
    grep -q 'data-page="logs"' templates/index.html && \
    grep -q 'id="page-logs"' templates/index.html && \
    grep -q 'teddy-logs.js' templates/index.html && \
    grep -q "'/api/logs'" teddy_logging.py && \
    ! grep -q 'MissAV' templates/index.html && \
    ! grep -q 'taskList.innerHTML = entries.map' templates/index.html

# 6. 폴더 생성 및 포트 노출
RUN mkdir -p /downloads
EXPOSE 5000

# 7. Teddy 안정성 + VPN 관리 + 웹 로그 레이어 실행
CMD ["python", "teddy_bootstrap.py"]
