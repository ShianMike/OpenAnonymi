# OpenAnonymi API: one container, one Uvicorn worker.
#
# Keep exactly one worker and one running instance. Sign-in, registration and recovery
# attempt limits (app/accounts/api.py AttemptLimiter) and review undo history
# (app/groups/service.py _undo) live in process memory. Extra workers or replicas would
# each keep their own copy, and a restart clears them.
#
# Build from this directory:  docker build -t openanonymi-api backend

FROM python:3.11-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.6 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
# Locked runtime dependencies only, including spaCy 3.8 and the en_core_web_sm 3.8.0 model.
RUN uv sync --locked --no-dev --no-install-project --no-cache
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
RUN /app/.venv/bin/python -m compileall -q app migrations

FROM python:3.11-slim
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PRIVACY_REVIEW_ENVIRONMENT=production
RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
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
