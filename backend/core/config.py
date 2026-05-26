"""Application configuration from environment variables."""
import logging
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
    secret_key: str = ""  # REQUIRED: set SECRET_KEY in environment
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

    # SECURITY-REVIEW: JWT config for auth tokens
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    @property
    def is_production(self) -> bool:
        """True when environment == 'production'."""
        return self.environment == "production"

    def validate_startup(self) -> None:
        """Validate critical config on startup. Raises ValueError if invalid."""
        # SECURITY-REVIEW: Enforce SECRET_KEY presence and strength
        if not self.secret_key or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be set in environment and >= 32 characters long. "
                "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        
        if self.is_production:
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required in production")
            if "localhost" in self.database_url:
                raise ValueError("Cannot use localhost database URL in production")


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
    settings = Settings()
    settings.validate_startup()
    return settings

    Reads from .env file at first call, validates all settings, and caches result.
    Subsequent calls return cached instance.

settings = get_settings()

