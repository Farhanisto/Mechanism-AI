from fastapi import APIRouter
from pydantic import BaseModel

from app.ai.meta_client import DEFAULT_META_MODEL
from app.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    ai_enabled: bool
    model: str | None = None


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service="mechanism-ai-api",
        version="0.1.0",
        ai_enabled=settings.meta_api_key is not None,
        model=settings.meta_model or DEFAULT_META_MODEL,
    )
