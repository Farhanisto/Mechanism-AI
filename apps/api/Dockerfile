FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends libegl1 libgl1 libglu1-mesa libosmesa6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/apps/api

COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --extra sim --extra cad

COPY apps/api/app ./app
COPY apps/api/docker-entrypoint.sh /app/apps/api/docker-entrypoint.sh
COPY apps/api/run_server.py /app/apps/api/run_server.py
RUN chmod +x /app/apps/api/docker-entrypoint.sh

ENV PORT=8000

EXPOSE 8000 8080

# Railway injects PORT=8080 at runtime; locally this falls back to 8000.
# The entrypoint listens on both IPv4 and IPv6 for Railway private networking.
CMD ["/app/apps/api/docker-entrypoint.sh"]
