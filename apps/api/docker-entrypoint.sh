#!/bin/sh
# Local Docker publishes IPv4; Railway's private network expects IPv6 (and
# resolves both IPv4/IPv6 in newer environments). Bind the right family
# automatically so docker compose and Railway both work.
set -eu

host="${HOST:-0.0.0.0}"
if [ -n "${RAILWAY_ENVIRONMENT:-}${RAILWAY_ENVIRONMENT_ID:-}" ]; then
    host="::"
fi

exec uv run --frozen --no-dev --extra sim --extra cad \
    uvicorn app.main:app --host "${host}" --port "${PORT:-8000}"
