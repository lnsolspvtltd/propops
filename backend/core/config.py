"""Application configuration via environment variables.

Uses Pydantic v2 settings with validation and type safety.
All config is read from .env at startup; immutable at runtime.
"""
import logging
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment."""

    # ── Core ─────────────────────────────────────────────────────────────────
    environment: str = Field(default="development", pattern="^(development|staging|production)$")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/propops")
    database_pool_size: int = Field(default=5, ge=1, le=100)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout: int = Field(default=30, ge=5)

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)

    # ── Security ─────────────────────────────────────────────────────────────
    secret_key: str = Field(default="dev-secret-key-change-in-production")
    allowed_origins: list[str] = Field(default=["http://localhost:3000"])

    # ── Integrations ─────────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(default=None)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses async driver."""
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("database_url must use postgresql+asyncpg:// (async) driver")
        return v

    @validator("allowed_origins")
    @classmethod
    def validate_origins(cls, v: list[str]) -> list[str]:
        """Reject wildcard origins in production."""
        if "*" in v and Settings().environment == "production":  # type: ignore
            raise ValueError("Wildcard CORS origins not allowed in production")
        return v


settings = Settings()

# Log config loaded (but never log secrets)
logger.info(
    "Config loaded: environment=%s, api=%s:%s, db_pool=%s/%s",
    settings.environment,
    settings.api_host,
    settings.api_port,
    settings.database_pool_size,
    settings.database_max_overflow,
)
---