"""Application configuration via environment variables.

Pydantic v2 Settings with full validation. All config loaded from .env at startup.

Key design decisions:
- get_settings() uses @lru_cache so Settings is instantiated once per process.
  Call get_settings.cache_clear() in tests to reset between test cases.
- All secrets are Optional at definition time; validators enforce requirements
  in production so development can run without all secrets configured.
- is_production property for environment-specific guards throughout the codebase.
"""
from functools import lru_cache
from typing import Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Usage::

        from backend.core.config import get_settings
        settings = get_settings()

    Testing::

        # Reset singleton between tests
        get_settings.cache_clear()
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]
    version: str = "0.1.0-alpha"

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """
        SECURITY-REVIEW: Enforce non-empty secret_key in production.
        Empty secret_key renders session/JWT security ineffective.
        """
        environment = info.data.get("environment", "development")
        if environment == "production" and not v:
            raise ValueError(
                "secret_key must be set via SECRET_KEY environment variable in production"
            )
        if environment == "development" and not v:
            import logging
            logging.getLogger(__name__).warning(
                "⚠️ CRITICAL: secret_key is empty in development. "
                "Set SECRET_KEY in .env for security testing. "
                "Production deployment will fail without this."
            )
        return v

    @model_validator(mode='after')
    def validate_production_secrets(self) -> 'Settings':
        """Raise if required secrets are missing in production."""
        if self.environment == 'production':
            if not self.secret_key:
                raise ValueError("SECRET_KEY must be set in production environment")
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY must be set in production environment")
        return self

    @property
    def is_production(self) -> bool:
        """True when environment == 'production'."""
        return self.environment == "production"

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v.lower()

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Reject weak secrets in production."""
        data = info.data
        if data.get("environment") == "production":
            if len(v) < 32 or v.startswith("dev-"):
                raise ValueError(
                    "secret_key must be 32+ characters and NOT start with 'dev-' "
                    "in production. Generate with: openssl rand -hex 32"
                )
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """database_url is required in production."""
        data = info.data
        if data.get("environment") == "production" and not v:
            raise ValueError(
                "database_url must be set explicitly in production. "
                "No default is provided."
            )
        return v

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: List[str], info) -> List[str]:
        """Block wildcard CORS in production."""
        data = info.data
        if data.get("environment") == "production" and "*" in v:
            raise ValueError(
                "cors_origins must NOT contain '*' in production. "
                "Use explicit origins."
            )
        return v

    @field_validator("debug")
    @classmethod
    def validate_debug(cls, v: bool, info) -> bool:
        """debug=True is not allowed in production."""
        data = info.data
        if data.get("environment") == "production" and v:
            raise ValueError("debug must be False in production environment")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application settings singleton.

    Uses lru_cache so Settings is only instantiated once per process.
    Raises ValidationError at startup if any required setting is invalid.

    For testing, call get_settings.cache_clear() between test cases.
    """
    return Settings()

    Reads from .env file at first call, validates all settings, and caches result.
    Subsequent calls return cached instance.

settings = get_settings()
