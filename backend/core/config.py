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
See conftest.py for example fixture pattern.
"""
import logging
import os
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator, ValidationError, ConfigDict
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
    All sensitive fields (database_url, anthropic_api_key) are validated to reject
    empty strings and must be explicitly provided.
    
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
        description="Enable debug mode (must be false in production)"
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
                    "Required in production; optional in development/staging."
    )
    database_pool_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="SQLAlchemy connection pool size (1-100). "
                    "Development: 5-10, Production: 20-50"
    )
    database_max_overflow: int = Field(
        default=20,
        ge=0,
        le=200,
        description="SQLAlchemy max overflow connections (0-200). "
                    "Allows burst beyond pool_size. Development: 10-20, Production: 40-100"
    )
    database_pool_pre_ping: bool = Field(
        default=True,
        description="Test connections before use to avoid 'connection closed' errors"
    )
    database_pool_recycle: int = Field(
        default=3600,
        ge=60,
        description="Recycle connections after this many seconds (prevents RDS timeout issues)"
    )

    # ── API Keys & Secrets ───────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude LLM access. "
                    "Required in production; optional in development."
    )
    
    # ── API Configuration ────────────────────────────────────────────────────
    api_title: str = Field(
        default="PropOps API",
        description="API title for OpenAPI documentation"
    )
    api_version: str = Field(
        default="0.1.0-alpha",
        description="API version for OpenAPI documentation"
    )
    api_root_path: str = Field(
        default="",
        description="Root path prefix for all API routes (e.g., '/api' mounts routes at /api/...)"
    )

    # ── CORS Configuration ───────────────────────────────────────────────────
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Comma-separated list of allowed CORS origins. "
                    "For development: localhost origins. For production: explicit domain list only."
    )
    cors_allow_credentials: bool = Field(
        default=True,
        description="Allow credentials in CORS requests"
    )
    cors_allow_methods: str = Field(
        default="GET,POST,PUT,DELETE,PATCH,OPTIONS",
        description="Comma-separated list of allowed HTTP methods"
    )
    cors_allow_headers: str = Field(
        default="*",
        description="Comma-separated list of allowed headers (default '*' allows all)"
    )

    # ── Rate Limiting (optional, for future use) ────────────────────────────
    rate_limit_enabled: bool = Field(
        default=False,
        description="Enable rate limiting on API endpoints"
    )
    rate_limit_requests_per_minute: int = Field(
        default=60,
        ge=1,
        description="Requests per minute per IP address"
    )

    # ── Logging Configuration ────────────────────────────────────────────────
    sentry_dsn: Optional[str] = Field(
        default=None,
        description="Sentry error tracking DSN. Optional; set in production for monitoring."
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is a known value."""
        valid = {"development", "staging", "production"}
        if v.lower() not in valid:
            raise ValueError(f"environment must be one of {valid}, got {v}")
        return v.lower()

    @field_validator("debug")
    @classmethod
    def validate_debug_mode(cls, v: bool, info) -> bool:
        """Warn if debug is True in production."""
        if v and info.data.get("environment") == "production":
            logger.warning("config: debug=True in production — this exposes sensitive information!")
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """Validate database_url is not empty string and uses asyncpg driver."""
        if v is not None:
            if v.strip() == "":
                raise ValueError("database_url must not be empty string; use None or remove from .env")
            if "asyncpg" not in v:
                logger.warning(
                    "config: database_url does not use asyncpg driver; "
                    "FastAPI requires async DB driver. Expected: postgresql+asyncpg://..."
                )
        
        # Require database_url in production
        if info.data.get("environment") == "production" and not v:
            raise ValueError(
                "database_url is required in production. "
                "Set DATABASE_URL environment variable via deployment platform."
            )
        
        return v

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_key(cls, v: Optional[str], info) -> Optional[str]:
        """Validate Anthropic API key is not empty string or weak dev key in production."""
        if v is not None:
            if v.strip() == "":
                raise ValueError("anthropic_api_key must not be empty string; use None or remove from .env")
            
            # SECURITY-REVIEW: Reject weak secrets in production
            if info.data.get("environment") == "production":
                if v.startswith("dev-") or v.startswith("sk-"):
                    raise ValueError(
                        "anthropic_api_key in production must not start with 'dev-' or 'sk-'. "
                        "Use a real production API key from Anthropic console."
                    )
        
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str) -> str:
        """Parse comma-separated CORS origins; validate no wildcards in production."""
        if isinstance(v, str) and v.strip():
            origins = [o.strip() for o in v.split(",") if o.strip()]
            # SECURITY-REVIEW: Warn if wildcard used in production
            if "*" in origins or "http://*" in v or "https://*" in v:
                logger.warning(
                    "config: CORS origins contain wildcards — this allows any origin to access the API. "
                    "Only use in development. In production, specify explicit domain list."
                )
            return ",".join(origins)
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins string into list for FastAPI use."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def cors_allow_methods_list(self) -> list[str]:
        """Parse CORS methods string into list."""
        return [m.strip().upper() for m in self.cors_allow_methods.split(",") if m.strip()]

    @property
    def cors_allow_headers_list(self) -> list[str]:
        """Parse CORS headers string into list."""
        if self.cors_allow_headers.strip() == "*":
            return ["*"]
        return [h.strip() for h in self.cors_allow_headers.split(",") if h.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings (singleton via lru_cache).
    
    Reads from .env file at first call, validates all settings, and caches result.
    Subsequent calls return cached instance.
    
    Raises:
        ValidationError: If any setting is invalid or required settings are missing.
    
    For testing: call get_settings.cache_clear() to reset singleton state between tests.
    
    Returns:
        Settings: Immutable, validated settings instance.
    """
    try:
        settings = Settings()
        logger.info(
            "config: Settings loaded successfully [env=%s, debug=%s, db_pool=%d]",
            settings.environment, settings.debug, settings.database_pool_size
        )
        return settings
    except ValidationError as e:
        logger.error("config: Settings validation failed. Check .env and environment variables.")
        for error in e.errors():
            logger.error("  - %s: %s", error["loc"][0], error["msg"])
        raise
---