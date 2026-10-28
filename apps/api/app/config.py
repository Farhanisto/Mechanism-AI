from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    cors_origins: list[str] = ["http://localhost:5173"]
    max_candidates: int = Field(default=3, ge=1, le=3)
    max_run_seconds: float = Field(default=60.0, gt=0, le=600)
    meta_api_base_url: str | None = None
    meta_api_key: SecretStr | None = None
    meta_model: str | None = None
    meta_reasoning_effort: Literal["minimal", "low", "medium", "high", "xhigh", "max"] = "minimal"
    meta_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    meta_max_retries: int = Field(default=1, ge=0, le=3)
    meta_max_output_tokens: int = Field(default=8192, ge=256, le=8192)

    @field_validator("meta_api_base_url", "meta_api_key", "meta_model", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
