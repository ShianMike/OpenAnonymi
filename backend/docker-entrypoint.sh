#!/bin/sh
# Validate configuration without touching the database, apply migrations, then serve.
#
# One worker for the model's memory budget; limits and undo are in PostgreSQL.
# --no-access-log: app.edge.AccessLogMiddleware logs route templates without query strings.
# --no-proxy-headers: the client address comes only from PRIVACY_REVIEW_TRUSTED_PROXY_HOPS.
set -eu

python -m app.check_config
alembic upgrade head

exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --no-access-log \
    --no-proxy-headers \
    --no-server-header \
    --timeout-keep-alive 90 \
    --timeout-graceful-shutdown 25
