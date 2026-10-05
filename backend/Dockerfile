# OpenAnonymi API: one container, one Uvicorn worker.
#
# Keep one worker and one instance for the spaCy model's memory budget on Free hosting.
# Attempt limits and bounded review undo history are shared in PostgreSQL and survive
# restarts. Each additional worker would load its own local language model.
#
# Build from this directory:  docker build -t openanonymi-api backend

FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/
# Build the locked Pillow source against current TIFF fixes, rather than the
# wheel's older bundled libtiff. Other codec libraries receive Debian updates.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates libjpeg62-turbo-dev zlib1g-dev \
    libwebp-dev libfreetype6-dev liblcms2-dev liblzma-dev libzstd-dev \
    libdeflate-dev libjbig-dev liblerc-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/native
RUN curl --fail --location --proto '=https' --tlsv1.2 \
    https://download.osgeo.org/libtiff/tiff-4.7.2.tar.gz -o tiff.tar.gz \
    && echo '672bd7d10aee4606171afb864f3570b83340f6a33e2c186dc0512f7145ffdf6a  tiff.tar.gz' | sha256sum --check \
    && tar -xzf tiff.tar.gz \
    && cd tiff-4.7.2 \
    && ./configure --prefix=/usr --disable-static --disable-tools --disable-tests --disable-contrib --disable-docs \
    && make -j2 && make install && ldconfig
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# Locked runtime dependencies only, including spaCy 3.8 and the en_core_web_sm 3.8.0 model.
RUN uv sync --locked --no-dev --no-install-project --no-cache --no-binary-package pillow \
    --config-settings-package pillow:tiff=enable \
    --config-settings-package pillow:webp=enable \
    --config-settings-package pillow:freetype=enable
RUN /app/.venv/bin/python -c "from PIL import features; assert features.version('libtiff') == '4.7.2'; assert all(features.check(f) for f in ('jpg', 'zlib', 'webp', 'freetype2'))"
COPY native-runtime.json ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY certs ./certs
RUN /app/.venv/bin/python -m compileall -q app migrations

FROM python:3.11-slim
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PRIVACY_REVIEW_ENVIRONMENT=production
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g libwebp7 libwebpdemux2 libwebpmux3 libfreetype6 \
    liblcms2-2 liblzma5 libzstd1 libdeflate0 libjbig0 liblerc4 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
COPY --from=build /usr/lib/libtiff.so* /usr/lib/
COPY --from=build /tmp/native/tiff-4.7.2/LICENSE.md /usr/share/doc/openanonymi-libtiff/LICENSE.md
RUN ldconfig
WORKDIR /app
COPY --from=build /app /app
COPY docker-entrypoint.sh /usr/local/bin/openanonymi-start
RUN sed -i 's/\r$//' /usr/local/bin/openanonymi-start && chmod 0755 /usr/local/bin/openanonymi-start
USER app
EXPOSE 8000
# Process liveness only; readiness (GET /api/v1/health/ready) also checks PostgreSQL.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/v1/health/live', timeout=4)"]
ENTRYPOINT ["openanonymi-start"]
