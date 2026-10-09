# OpenAnonymi website and API: one container, one Uvicorn worker.
#
# Keep one worker and one instance; each worker loads its own spaCy model.
# Attempt limits and bounded review undo history are shared in PostgreSQL and survive
# restarts. Each additional worker would load its own local language model.
#
# Build from the repository root: docker build -t openanonymi-api .

FROM node:24-slim AS website
WORKDIR /website
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/index.html frontend/vite.config.ts frontend/tsconfig*.json ./
COPY frontend/src ./src
COPY frontend/public ./public
RUN npm run build

FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/
# Build the locked Pillow source against current TIFF fixes, rather than the
# wheel's older bundled libtiff. Other codec libraries receive Debian updates.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake pkg-config curl ca-certificates libjpeg62-turbo-dev zlib1g-dev \
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
# OCR receives raw pixels from Pillow/PDFium; Leptonica needs no image codecs.
RUN curl --fail --location --proto '=https' --tlsv1.2 \
    https://github.com/DanBloomberg/leptonica/releases/download/1.87.0/leptonica-1.87.0.tar.gz -o leptonica.tar.gz \
    && echo 'c73363397f96eb1295602bf44d708a994ad42046c791bf03ea0505d829bdb6a7  leptonica.tar.gz' | sha256sum --check \
    && tar -xzf leptonica.tar.gz \
    && cd leptonica-1.87.0 \
    && ./configure --prefix=/usr --libdir=/usr/lib --disable-static --disable-programs \
        --without-zlib --without-libpng --without-jpeg --without-giflib --without-libtiff \
        --without-libwebp --without-libwebpmux --without-libopenjpeg \
    && make -j2 && make install && ldconfig
RUN curl --fail --location --proto '=https' --tlsv1.2 \
    https://github.com/tesseract-ocr/tesseract/archive/refs/tags/5.5.3.tar.gz -o tesseract.tar.gz \
    && echo '9218e62793116d42a9f6d14cd9348518b27f382096eea3d0f2d1a24616bb5884  tesseract.tar.gz' | sha256sum --check \
    && tar -xzf tesseract.tar.gz \
    && cmake -S tesseract-5.5.3 -B tesseract-build -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=ON \
        -DBUILD_TRAINING_TOOLS=OFF -DBUILD_TESTS=OFF -DOPENMP_BUILD=OFF \
        -DGRAPHICS_DISABLED=ON -DDISABLE_TIFF=ON \
        -DDISABLE_ARCHIVE=ON -DDISABLE_CURL=ON -DINSTALL_CONFIGS=OFF \
    && cmake --build tesseract-build --parallel 2 \
    && cmake --install tesseract-build && ldconfig
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
# Locked runtime dependencies only, including spaCy 3.8 and the en_core_web_sm 3.8.0 model.
RUN uv sync --locked --no-dev --no-install-project --no-cache \
    --no-binary-package pillow --no-binary-package tesserocr \
    --config-settings-package pillow:tiff=enable \
    --config-settings-package pillow:webp=enable \
    --config-settings-package pillow:freetype=enable
RUN /app/.venv/bin/python -c "from PIL import features; assert features.version('libtiff') == '4.7.2'; assert all(features.check(f) for f in ('jpg', 'zlib', 'webp', 'freetype2'))"
COPY backend/native-runtime.json ./
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/app ./app
COPY backend/certs ./certs
RUN /app/.venv/bin/python -m compileall -q app migrations

FROM python:3.11-slim
LABEL org.opencontainers.image.source="https://github.com/ShianMike/OpenAnonymi" \
    org.opencontainers.image.licenses="AGPL-3.0-or-later"
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
COPY --from=build /usr/lib/libleptonica.so* /usr/lib/libtesseract.so* /usr/lib/
COPY --from=build /tmp/native/tiff-4.7.2/LICENSE.md /usr/share/doc/openanonymi-libtiff/LICENSE.md
COPY --from=build /tmp/native/leptonica-1.87.0/leptonica-license.txt /usr/share/doc/openanonymi-leptonica/LICENSE
COPY --from=build /tmp/native/tesseract-5.5.3/LICENSE /usr/share/doc/openanonymi-tesseract/LICENSE
RUN ldconfig
WORKDIR /app
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md /usr/share/doc/openanonymi/
COPY --from=build /app /app
COPY --from=website /website/dist /app/frontend
COPY backend/docker-entrypoint.sh /usr/local/bin/openanonymi-start
RUN sed -i 's/\r$//' /usr/local/bin/openanonymi-start && chmod 0755 /usr/local/bin/openanonymi-start
USER app
EXPOSE 8000
# Process liveness only; readiness (GET /api/v1/health/ready) also checks PostgreSQL.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/v1/health/live', timeout=4)"]
CMD ["openanonymi-start"]
