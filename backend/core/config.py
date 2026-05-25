"""Application configuration via environment variables.

Uses Pydantic v2 settings with validation and type safety.
All config is read from .env at startup; immutable at runtime.
All secrets must be provided explicitly — no hardcoded defaults in production.

Singleton pattern via lru_cache ensures settings are instantiated once and reused,
avoiding repeated validation overhead and ensuring consistent configuration throughout
the application lifecycle.

For testing, call get_settings.cache_clear() in test fixtures to reset singleton state.
"""
import logging
import sys
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

    @field_validator("environment", mode="after")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment is a known value."""
        if v not in ("development", "staging", "production"):
            raise ValueError(
                f"environment must be one of: development, staging, production. Got: {v}"
            )
        return v

    @field_validator("debug", mode="after")
    @classmethod
    def validate_debug_mode(cls, v: bool, info) -> bool:
        """SECURITY-REVIEW: Block debug mode in production.
        
        Debug mode enables detailed error pages, full stack traces, and verbose logging.
        This is a critical security risk in production (information disclosure).
        """
        environment = info.data.get("environment")
        if v and environment == "production":
            raise ValueError(
                "debug=True is not allowed in production environment. "
                "Set DEBUG=false in .env or deployment platform."
            )
        return v

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """SECURITY-REVIEW: Reject weak secrets in production.
        
        In production, secret key must:
        - Not start with 'dev-' (development marker)
        - Be at least 32 characters (cryptographic strength)
        - Not use common test values
        
        Development (default: dev-secret-key-local-testing-only) is permitted for local dev.
        """
        environment = info.data.get("environment")
        
        if environment == "production":
            if v.startswith("dev-"):
                raise ValueError(
                    "secret_key must not start with 'dev-' in production. "
                    "Generate a strong random key with: openssl rand -hex 32"
                )
            if len(v) < 32:
                raise ValueError(
                    "secret_key must be at least 32 characters in production. "
                    "Generate with: openssl rand -hex 32"
                )
            if v == "dev-secret-key-local-testing-only":
                raise ValueError(
                    "secret_key uses default development value in production. "
                    "This is a critical security error. "
                    "Generate and set a unique strong key in your deployment platform."
                )
        
        return v

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """SECURITY-REVIEW: Reject weak JWT secrets in production.
        
        In production, JWT secret must:
        - Not start with 'dev-' (development marker)
        - Be at least 32 characters (cryptographic strength)
        - Not use common test values
        
        Development (default: dev-jwt-secret-local-testing-only) is permitted for local dev.
        """
        environment = info.data.get("environment")
        
        if environment == "production":
            if v.startswith("dev-"):
                raise ValueError(
                    "jwt_secret must not start with 'dev-' in production. "
                    "Generate a strong random key with: openssl rand -hex 32"
                )
            if len(v) < 32:
                raise ValueError(
                    "jwt_secret must be at least 32 characters in production. "
                    "Generate with: openssl rand -hex 32"
                )
            if v == "dev-jwt-secret-local-testing-only":
                raise ValueError(
                    "jwt_secret uses default development value in production. "
                    "This is a critical security error. "
                    "Generate and set a unique strong key in your deployment platform."
                )
        
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """SECURITY-REVIEW: Require explicit database URL in production.
        
        DATABASE_URL is critical and has no safe default:
        - Empty string or None in production is caught here and raises ValueError
        - Development allows None (in-memory test DBs)
        - All URLs must use asyncpg driver (postgresql+asyncpg://)
        
        Fail fast with clear message if DATABASE_URL is not set in production.
        """
        environment = info.data.get("environment")
        
        if environment == "production" and not v:
            raise ValueError(
                "DATABASE_URL is required in production environment. "
                "Set DATABASE_URL in your deployment platform (Railway, Heroku, etc). "
                "Format: postgresql+asyncpg://user:password@host:port/database"
            )
        
        if v and "postgresql+asyncpg" not in v:
            raise ValueError(
                f"DATABASE_URL must use asyncpg driver. "
                f"Format: postgresql+asyncpg://user:password@host:port/database. "
                f"Current: {v[:50]}..."
            )
        
        return v

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def validate_allowed_origins(cls, v: list[str], info) -> list[str]:
        """SECURITY-REVIEW: Block wildcard CORS origins in production.
        
        Wildcard origins (*) in production allow any website to make cross-origin
        requests on behalf of users (CSRF attack). This is a critical security risk.
        
        Production must use explicit origins list (app.example.com, etc).
        Development allows localhost:* for ease of testing.
        """
        environment = info.data.get("environment")
        
        if environment == "production" and "*" in v:
            raise ValueError(
                "Wildcard CORS origins (*) are not allowed in production. "
                "Set explicit origins in ALLOWED_ORIGINS: "
                "https://app.propops.com,https://dashboard.propops.com"
            )
        
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings factory with LRU cache.
    
    Returns the same Settings instance on repeated calls to avoid:
    - Repeated .env file reads
    - Repeated validation overhead
    - Inconsistent configuration mid-request
    
    Thread-safe: lru_cache uses a lock internally.
    
    For testing, call get_settings.cache_clear() in test fixtures to reset:
    ```python
    @pytest.fixture(autouse=True)
    def reset_settings():
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()
    ```
    
    Raises:
        ValidationError: If environment variables fail Pydantic validation
                        (missing required fields, invalid types, etc).
    """
    try:
        settings = Settings()
        logger.info(
            f"✓ Settings loaded successfully "
            f"(environment={settings.environment}, debug={settings.debug})"
        )
        return settings
    except ValidationError as e:
        logger.error(
            f"✗ Settings validation failed. "
            f"Check your .env file or environment variables. "
            f"Errors: {e.error_count()} validation error(s)."
        )
        # Print detailed validation errors to stderr for deployment debugging
        for error in e.errors():
            logger.error(f"  {error['loc'][0]}: {error['msg']}")
        raise


if __name__ == "__main__":
    # Quick validation check: python -m backend.core.config
    try:
        settings = get_settings()
        print("✓ Settings valid")
        print(f"  Environment: {settings.environment}")
        print(f"  Debug: {settings.debug}")
        print(f"  Database: {settings.database_url[:50] if settings.database_url else '(not set)'}...")
        sys.exit(0)
    except ValidationError as e:
        print("✗ Settings validation failed")
        for error in e.errors():
            print(f"  {error['loc'][0]}: {error['msg']}")
        sys.exit(1)
---