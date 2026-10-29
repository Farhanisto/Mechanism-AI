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

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-dev", "--extra", "sim", "--extra", "cad", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
