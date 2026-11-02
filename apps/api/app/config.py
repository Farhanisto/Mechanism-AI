import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CORS_ORIGINS = ["http://localhost:5173"]


def _parse_origins(value: object) -> list[str]:
    """Accept a JSON array, a bare URL, or a comma-separated list of origins."""
    if value is None:
        return list(DEFAULT_CORS_ORIGINS)
    if isinstance(value, (list, tuple, set)):
        candidates = [str(item) for item in value]
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return list(DEFAULT_CORS_ORIGINS)
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, list):
            candidates = [str(item) for item in decoded]
        elif isinstance(decoded, str):
            candidates = [decoded]
        else:
            # Railway/dashboard users often paste a bare URL or comma-separated list.
            candidates = text.strip("[]").split(",")
    else:
        return list(DEFAULT_CORS_ORIGINS)

    origins = [
        candidate.strip().strip("'\"").rstrip("/")
        for candidate in candidates
        if candidate.strip().strip("'\"")
    ]
    return origins or list(DEFAULT_CORS_ORIGINS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MECHANISM_AI_",
        env_file=(REPO_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Mechanism AI"
    api_prefix: str = "/api/v1"
    artifacts_dir: Path = REPO_ROOT / "data" / "artifacts"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(DEFAULT_CORS_ORIGINS)
    )
    max_candidates: int = Field(default=3, ge=1, le=3)
    max_run_seconds: float = Field(default=60.0, gt=0, le=600)
    simulation_engine: Literal["auto", "reference", "mujoco"] = "auto"
    meta_api_base_url: str | None = None
    meta_api_key: SecretStr | None = None
    meta_model: str | None = None
    meta_reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh", "max"] = "minimal"
    meta_timeout_seconds: float | None = Field(default=None, gt=0, le=3600)
    meta_max_retries: int = Field(default=1, ge=0, le=3)
    meta_max_output_tokens: int = Field(default=16384, ge=256, le=16384)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> list[str]:
        return _parse_origins(value)

    @field_validator(
        "meta_api_base_url",
        "meta_api_key",
        "meta_model",
        "meta_timeout_seconds",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
