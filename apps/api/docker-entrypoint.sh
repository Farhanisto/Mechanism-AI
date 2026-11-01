#!/bin/sh
# Bind both IPv4 and IPv6. Railway private DNS can return A and AAAA records and
# nginx may choose either; binding both avoids intermittent connection refusals.
set -eu

exec uv run --frozen --no-dev --extra sim --extra cad python /app/apps/api/run_server.py
