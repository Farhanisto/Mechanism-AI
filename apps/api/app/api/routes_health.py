from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.ai.meta_client import DEFAULT_META_MODEL, MetaModelError
from app.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    ai_enabled: bool
    model: str | None = None


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = get_settings()
    orchestrator = getattr(request.app.state, "orchestrator", None)
    client = getattr(orchestrator, "meta_client", None)
    effective_model = getattr(client, "model", None)
    return HealthResponse(
        status="ok",
        service="mechanism-ai-api",
        version="0.1.0",
        ai_enabled=bool(getattr(client, "is_configured", False)),
        model=effective_model or settings.meta_model or DEFAULT_META_MODEL,
    )


@router.get("/provider/models")
async def provider_models(request: Request) -> dict[str, object]:
    """List the models the configured API key can use (no secrets returned)."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    client = getattr(orchestrator, "meta_client", None)
    if client is None or not client.is_configured:
        return {"configured": False, "model": None, "models": []}
    try:
        models = await client.list_models()
    except MetaModelError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"configured": True, "model": client.model, "models": models}
