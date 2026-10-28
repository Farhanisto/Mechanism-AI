from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.meta_client import build_meta_client
from app.api import routes_artifacts, routes_design_runs, routes_health
from app.config import get_settings
from app.orchestration.design_run import DesignRunOrchestrator, EventBroker, RunStore
from app.persistence.artifacts import ArtifactStore

API_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    artifacts = ArtifactStore(settings.artifacts_dir)
    store = RunStore(artifacts)
    events = EventBroker()
    meta_client = build_meta_client(settings)
    app.state.orchestrator = DesignRunOrchestrator(
        store=store,
        events=events,
        artifacts=artifacts,
        meta_client=meta_client,
        max_candidates=settings.max_candidates,
        max_run_seconds=settings.max_run_seconds,
        limits={
            "server_max_candidates": settings.max_candidates,
            "meta_reasoning_effort": settings.meta_reasoning_effort,
            "meta_timeout_seconds": settings.meta_timeout_seconds,
            "meta_max_retries": settings.meta_max_retries,
            "meta_max_output_tokens": settings.meta_max_output_tokens,
            "prompt_max_characters": 4000,
        },
    )
    try:
        yield
    finally:
        await meta_client.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=API_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_health.router, prefix=settings.api_prefix)
    app.include_router(routes_design_runs.router, prefix=settings.api_prefix)
    app.include_router(routes_artifacts.router, prefix=settings.api_prefix)
    return app


app = create_app()
