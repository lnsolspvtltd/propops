"""Application configuration via environment variables.

Uses Pydantic v2 settings with validation and type safety.
All config is read from .env at startup; immutable at runtime.
All secrets must be provided explicitly — no hardcoded defaults in production.

Singleton pattern via lru_cache ensures settings are instantiated once and reused,
avoiding repeated validation overhead and ensuring consistent configuration throughout
the application lifecycle.

Settings validation is eager: get_settings() is called at app startup to fail fast
with clear error messages if configuration is invalid or missing required secrets.

For testing, call get_settings.cache_clear() in test fixtures to reset singleton state.
"""
import logging
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment.
    
    Pydantic v2 config using BaseSettings for automatic .env loading.
    All fields use Field() with validation to ensure type safety and sane defaults.
    Secrets validation ensures weak defaults are not used in production.
    
    Instantiate via get_settings() to guarantee singleton behavior and proper
    error handling at application startup.
    
    SECURITY-REVIEW: Weak secrets (starting with 'dev-') are rejected in production
    environments. Validators check environment == "production" and enforce strong keys.
    No hardcoded production secrets exist anywhere in codebase.
    
    Test Pattern:
    ```python
    @pytest.fixture(autouse=True)
    def reset_settings():
        get_settings.cache_clear()  # Reset singleton between tests
        yield
        get_settings.cache_clear()
    ```
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # ── Core ─────────────────────────────────────────────────────────────────
    environment: str = Field(
        default="development",
        pattern="^(development|staging|production)$",
        description="Deployment environment (development, staging, or production)"
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode (never in production)"
    )
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level"
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL async connection string (postgresql+asyncpg://user:password@host:port/db). "
                    "REQUIRED — must be set explicitly; no production default provided."
    )
    database_pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Connection pool size"
    )
    database_max_overflow: int = Field(
        default=10,
        ge=0,
        le=100,
        description="Pool overflow size"
    )
    database_pool_timeout: int = Field(
        default=30,
        ge=5,
        description="Pool timeout in seconds"
    )
    database_ssl_mode: str = Field(
        default="disable",
        pattern="^(require|prefer|disable)$",
        description="PostgreSQL SSL mode (require, prefer, or disable)"
    )

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = Field(
        default="0.0.0.0",
        description="Server bind address"
    )
    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Server port"
    )

    # ── Security ─────────────────────────────────────────────────────────────
    # SECURITY-REVIEW: All secret keys must be non-empty and strong in production.
    # Development defaults are intentionally weak for local testing only.
    # Validators below ensure weak keys are rejected in production.
    # No hardcoded production secrets exist anywhere in this file.
    secret_key: str = Field(
        default="dev-secret-key-local-testing-only",
        min_length=8,
        description="Application secret key (change in production)"
    )
    jwt_secret: str = Field(
        default="dev-jwt-secret-local-testing-only",
        min_length=8,
        description="JWT signing secret (separate from SECRET_KEY)"
    )
    jwt_access_token_expiry: int = Field(
        default=900,
        ge=60,
        le=86400,
        description="Access token TTL in seconds (default: 15 minutes)"
    )
    jwt_refresh_token_expiry: int = Field(
        default=604800,
        ge=3600,
        le=2592000,
        description="Refresh token TTL in seconds (default: 7 days)"
    )
    allowed_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins (comma-separated, no wildcards in production)"
    )

    # ── Integrations ─────────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic Claude API key (optional — required only if AI features enabled)"
    )
    supabase_url: Optional[str] = Field(
        default=None,
        description="Supabase project URL (optional — required only if Supabase backend enabled)"
    )
    supabase_service_key: Optional[str] = Field(
        default=None,
        description="Supabase service role key (never use anon key; required only if Supabase backend enabled)"
    )
    imap_host: Optional[str] = Field(
        default=None,
        description="IMAP server hostname for email ingestion (optional)"
    )
    imap_port: int = Field(
        default=993,
        ge=1,
        le=65535,
        description="IMAP server port (default: 993 for IMAPS)"
    )
    imap_username: Optional[str] = Field(
        default=None,
        description="IMAP username for authentication (optional)"
    )
    imap_password: Optional[str] = Field(
        default=None,
        description="IMAP password for authentication (optional, never hardcoded, set via deployment platform)"
    )

    @field_validator("environment", mode="after")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of allowed values."""
        if v not in ("development", "staging", "production"):
            raise ValueError(f"environment must be one of: development, staging, production. Got: {v}")
        return v

    @field_validator("debug", mode="after")
    @classmethod
    def validate_debug_disabled_in_production(cls, v: bool, info) -> bool:
        """Enforce debug=False in production for security."""
        environment = info.data.get("environment", "development")
        if v and environment == "production":
            raise ValueError("debug=True is not allowed in production environment")
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url_required_in_production(cls, v: Optional[str], info) -> Optional[str]:
        """Enforce database_url is set in production and non-development."""
        environment = info.data.get("environment", "development")
        if environment != "development" and not v:
            raise ValueError(f"database_url is required in {environment} environment; cannot be None")
        return v

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key_strength_in_production(cls, v: str, info) -> str:
        """Enforce strong secret keys in production and staging.
        
        SECURITY-REVIEW: Weak secrets (dev-*) are rejected in non-development.
        This prevents accidental use of development secrets in production.
        """
        environment = info.data.get("environment", "development")
        if environment in ("staging", "production"):
            if v.startswith("dev-") or len(v) < 32:
                raise ValueError(
                    f"secret_key must be strong in {environment}. "
                    f"Weak defaults (dev-*) and short keys (<32 chars) are rejected. "
                    f"Generate with: openssl rand -hex 32"
                )
        return v

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret_strength_in_production(cls, v: str, info) -> str:
        """Enforce strong JWT secrets in production and staging.
        
        SECURITY-REVIEW: Weak secrets (dev-*) are rejected in non-development.
        This prevents accidental use of development secrets in production.
        """
        environment = info.data.get("environment", "development")
        if environment in ("staging", "production"):
            if v.startswith("dev-") or len(v) < 32:
                raise ValueError(
                    f"jwt_secret must be strong in {environment}. "
                    f"Weak defaults (dev-*) and short keys (<32 chars) are rejected. "
                    f"Generate with: openssl rand -hex 32"
                )
        return v

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v) -> list[str]:
        """Parse comma-separated origins string into list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def validate_allowed_origins_no_wildcard_in_production(cls, v: list[str], info) -> list[str]:
        """Prevent wildcard CORS origins in production for security.
        
        SECURITY-REVIEW: Wildcard origins allow any domain to access the API.
        Only explicitly list trusted origins in production.
        """
        environment = info.data.get("environment", "development")
        if environment == "production":
            for origin in v:
                if "*" in origin:
                    raise ValueError(
                        f"allowed_origins cannot contain wildcards (*) in production. "
                        f"Explicitly list trusted origins only. Got: {v}"
                    )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings (singleton pattern).
    
    Loads and validates configuration from .env on first call.
    Subsequent calls return cached instance for performance.
    
    Raises:
        ValidationError: If configuration is invalid or required values are missing.
        This error is logged immediately with full context for debugging.
    
    Test Usage:
        Call get_settings.cache_clear() in pytest fixtures to reset singleton state
        between tests, allowing each test to have isolated configuration.
    
    Startup Usage:
        Call get_settings() eagerly in app lifespan context manager to fail fast
        with clear error messages if configuration is invalid. Never delay validation
        to the first request (that causes user-facing errors).
    """
    try:
        settings = Settings()
        logger.info(
            f"Configuration loaded: environment={settings.environment}, "
            f"debug={settings.debug}, database_url={'***' if settings.database_url else 'NOT SET'}"
        )
        return settings
    except ValidationError as e:
        logger.error(
            f"Configuration validation failed at startup. "
            f"Please check your .env file and environment variables. "
            f"Errors:\n{e}",
            exc_info=True
        )
        raise
---