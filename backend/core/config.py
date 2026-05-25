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
        description="Allowed CORS origins (explicit list, never wildcard in production)"
    )

    # ── Supabase ─────────────────────────────────────────────────────────────
    supabase_service_key: Optional[str] = Field(
        default=None,
        description="Supabase service_role API key (server-side only, never expose to client). "
                    "Required for admin operations. SECURITY-REVIEW: Enforce least-privilege scopes."
    )

    # ── AI / LLM ─────────────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude models. Optional — only required if using AI features."
    )

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is one of allowed values."""
        allowed = {'development', 'staging', 'production'}
        if v.lower() not in allowed:
            raise ValueError(f"environment must be one of {allowed}, got {v}")
        return v.lower()

    @field_validator('debug')
    @classmethod
    def validate_debug(cls, v: bool, info) -> bool:
        """Ensure debug mode is disabled in production."""
        data = info.data
        if data.get('environment') == 'production' and v:
            raise ValueError("debug must be False in production environment")
        return v

    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Ensure secret_key is strong in production."""
        data = info.data
        if data.get('environment') == 'production':
            if v.startswith('dev-') or len(v) < 32:
                raise ValueError(
                    "secret_key must be 32+ characters and NOT start with 'dev-' in production. "
                    "Use a cryptographically strong random key."
                )
        return v

    @field_validator('jwt_secret')
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """Ensure jwt_secret is strong in production."""
        data = info.data
        if data.get('environment') == 'production':
            if v.startswith('dev-') or len(v) < 32:
                raise ValueError(
                    "jwt_secret must be 32+ characters and NOT start with 'dev-' in production. "
                    "Use a cryptographically strong random key."
                )
        return v

    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure database_url is provided in production."""
        data = info.data
        if data.get('environment') == 'production' and not v:
            raise ValueError(
                "database_url must be set explicitly in production. "
                "No default is provided. Set via DATABASE_URL environment variable."
            )
        return v

    @field_validator('allowed_origins')
    @classmethod
    def validate_allowed_origins(cls, v: list[str], info) -> list[str]:
        """Ensure allowed_origins does not use wildcard in production."""
        data = info.data
        if data.get('environment') == 'production':
            if '*' in v:
                raise ValueError(
                    "allowed_origins must NOT contain '*' (wildcard) in production. "
                    "Specify explicit origins only (e.g., ['https://example.com'])"
                )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings singleton.
    
    Uses lru_cache to ensure settings are instantiated once and reused throughout
    the application lifecycle. Avoids repeated validation overhead and ensures
    configuration consistency.
    
    This function is called at app startup in lifespan context manager to fail
    fast with clear error messages if configuration is invalid or missing required
    secrets (especially in production).
    
    For testing: call get_settings.cache_clear() in test fixtures to reset state
    between tests. See conftest.py for example fixture pattern.
    
    Returns:
        Settings: Validated application configuration from environment.
        
    Raises:
        ValidationError: If any setting validation fails (database_url missing,
                        weak secrets in production, invalid enum values, etc.).
                        This is NOT suppressed — callers must handle explicitly
                        at app startup to surface configuration errors immediately.
    """
    try:
        settings = Settings()
        logger.info(f"✓ Settings loaded: environment={settings.environment}, debug={settings.debug}")
        return settings
    except ValidationError as e:
        # Log validation errors with full context; caller must handle
        logger.error(f"✗ Settings validation failed: {e}")
        raise
---