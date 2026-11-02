import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.meta_client import (
    DEFAULT_META_API_BASE_URL,
    DEFAULT_META_MODEL,
    build_meta_client,
)
from app.api import routes_artifacts, routes_design_runs, routes_health
from app.config import get_settings
from app.orchestration.design_run import DesignRunOrchestrator, EventBroker, RunStore
from app.persistence.artifacts import ArtifactStore
from app.persistence.metadata import MetadataStore

API_VERSION = "0.1.0"
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    metadata = MetadataStore(settings.artifacts_dir / "metadata.sqlite3")
    artifacts = ArtifactStore(settings.artifacts_dir, metadata=metadata)
    artifacts.hydrate()
    store = RunStore(artifacts, metadata=metadata)
    store.hydrate()
    events = EventBroker()
    meta_client = build_meta_client(settings)
    if meta_client.is_configured:
        key = settings.meta_api_key.get_secret_value() if settings.meta_api_key else ""
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
        logger.info(
            "Meta model configured: model=%s base=%s key_fingerprint=%s",
            settings.meta_model or DEFAULT_META_MODEL,
            settings.meta_api_base_url or DEFAULT_META_API_BASE_URL,
            fingerprint,
        )
    else:
        logger.warning(
            "Meta model is NOT configured (MECHANISM_AI_META_API_KEY is unset). "
            "Runs will use the deterministic fallback."
        )
    app.state.orchestrator = DesignRunOrchestrator(
        store=store,
        events=events,
        artifacts=artifacts,
        meta_client=meta_client,
        max_candidates=settings.max_candidates,
        max_run_seconds=settings.max_run_seconds,
        simulation_engine=settings.simulation_engine,
        limits={
            "server_max_candidates": settings.max_candidates,
            "simulation_engine": settings.simulation_engine,
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
        metadata.close()


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
