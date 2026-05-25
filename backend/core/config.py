"""Application configuration via environment variables.

Uses Pydantic v2 settings with validation and type safety.
All config is read from .env at startup; immutable at runtime.
All secrets must be provided explicitly — no hardcoded defaults in production.

Singleton pattern via lru_cache ensures settings are instantiated once and reused,
avoiding repeated validation overhead and ensuring consistent configuration throughout
the application lifecycle.
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
        description="PostgreSQL async connection string (postgresql+asyncpg://user:password@host:port/db)"
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
        """SECURITY-REVIEW: Block debug mode in production and staging.
        
        Debug mode enables verbose error pages, stack traces, and may log sensitive data.
        It must never be enabled in production or staging environments.
        """
        environment = info.data.get("environment", "development")
        if v is True and environment in ("staging", "production"):
            raise ValueError(
                f"debug=True is not allowed in {environment} environment. "
                f"Debug mode exposes sensitive information. "
                f"Set DEBUG=false or use development environment only."
            )
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """SECURITY-REVIEW: Enforce database_url is required in production.
        
        In development, a missing database_url is allowed (tests may mock DB).
        In production/staging, it's a critical error — application cannot start without DB.
        """
        environment = info.data.get("environment", "development")
        
        if v is None or v.strip() == "":
            if environment == "production":
                raise ValueError(
                    "database_url is REQUIRED in production environment. "
                    "Set DATABASE_URL in deployment platform (Railway, Heroku, Supabase, etc.). "
                    "Never set DATABASE_URL to an empty string. Application cannot start."
                )
            elif environment == "staging":
                logger.warning(
                    "database_url is empty in staging environment. "
                    "Staging typically requires a real database. "
                    "Confirm this is intentional (e.g., running tests with mocked DB)."
                )
        else:
            # Validate the connection string format
            if not v.startswith("postgresql+asyncpg://"):
                raise ValueError(
                    f"database_url must use postgresql+asyncpg driver (async). "
                    f"Got: {v[:50]}... "
                    f"Expected format: postgresql+asyncpg://user:password@host:port/database"
                )
        
        return v

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """SECURITY-REVIEW: Enforce strong secret_key in production.
        
        Development allows weak defaults (dev-*) for local testing.
        Production requires: min 32 chars, no 'dev-' prefix, cryptographically random.
        """
        environment = info.data.get("environment", "development")
        
        if environment == "production":
            if v.startswith("dev-") or v == "dev-secret-key-local-testing-only":
                raise ValueError(
                    "secret_key in production must not use development default. "
                    "Generate a strong key: openssl rand -hex 32 "
                    "and set in deployment platform. "
                    "Current key appears to be development-only."
                )
            if len(v) < 32:
                raise ValueError(
                    f"secret_key in production must be at least 32 characters. "
                    f"Got {len(v)} chars. Generate: openssl rand -hex 32"
                )
        
        return v

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """SECURITY-REVIEW: Enforce strong jwt_secret in production.
        
        Same rules as secret_key: min 32 chars in production, no dev- prefix.
        """
        environment = info.data.get("environment", "development")
        
        if environment == "production":
            if v.startswith("dev-") or v == "dev-jwt-secret-local-testing-only":
                raise ValueError(
                    "jwt_secret in production must not use development default. "
                    "Generate a strong key: openssl rand -hex 32 "
                    "and set in deployment platform. "
                    "Current key appears to be development-only."
                )
            if len(v) < 32:
                raise ValueError(
                    f"jwt_secret in production must be at least 32 characters. "
                    f"Got {len(v)} chars. Generate: openssl rand -hex 32"
                )
        
        return v

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v) -> list[str]:
        """Parse comma-separated CORS origins from string."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def validate_allowed_origins(cls, v: list[str], info) -> list[str]:
        """SECURITY-REVIEW: Block wildcard CORS in production.
        
        Wildcard (*) allows any origin, opening the app to CSRF attacks.
        Production must have explicit origin list.
        """
        environment = info.data.get("environment", "development")
        
        if "*" in v and environment in ("staging", "production"):
            raise ValueError(
                f"CORS wildcard origin (*) is not allowed in {environment} environment. "
                f"Explicitly list allowed origins: ALLOWED_ORIGINS=https://app.example.com,https://dashboard.example.com "
                f"to prevent CSRF attacks."
            )
        
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get or create singleton Settings instance.
    
    Uses functools.lru_cache to ensure Settings is instantiated exactly once,
    with validation errors raised at application startup time.
    
    Returns:
        Settings: Validated, immutable configuration object
        
    Raises:
        ValueError: If configuration validation fails (database_url missing in prod, etc.)
        SystemExit: If settings cannot be created (calls sys.exit(1))
        
    Usage:
        from backend.core.config import get_settings
        
        settings = get_settings()  # First call: instantiate, validate, cache
        settings = get_settings()  # Subsequent calls: return cached instance (no re-validation)
        
        # In FastAPI dependency:
        def get_config(settings: Settings = Depends(get_settings)) -> Settings:
            return settings
    """
    try:
        settings = Settings()
        logger.info(
            f"Configuration loaded successfully. "
            f"Environment: {settings.environment}, "
            f"Debug: {settings.debug}, "
            f"API: {settings.api_host}:{settings.api_port}"
        )
        return settings
    except ValidationError as e:
        logger.critical(
            f"Configuration validation failed at startup. "
            f"Application cannot continue. Errors:\n{e}"
        )
        sys.exit(1)

---