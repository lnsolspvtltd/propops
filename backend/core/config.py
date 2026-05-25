"""Application configuration via environment variables.

Uses Pydantic v2 settings with validation and type safety.
All config is read from .env at startup; immutable at runtime.
All secrets must be provided explicitly — no hardcoded defaults in production.
"""
import logging
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, ValidationError

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment.
    
    Pydantic v2 config using BaseSettings for automatic .env loading.
    All fields use Field() with validation to ensure type safety and sane defaults.
    """

    # ── Core ─────────────────────────────────────────────────────────────────
    environment: str = Field(
        default="development",
        pattern="^(development|staging|production)$",
        description="Deployment environment"
    )
    debug: bool = Field(default=False, description="Enable debug mode (never in production)")
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level"
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="",
        description="PostgreSQL async connection string (postgresql+asyncpg://...)"
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
        description="PostgreSQL SSL mode"
    )

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", description="Server bind address")
    api_port: int = Field(default=8000, ge=1, le=65535, description="Server port")

    # ── Security ─────────────────────────────────────────────────────────────
    # SECURITY-REVIEW: All secret keys must be non-empty in production.
    # Development defaults are intentionally weak for local testing only.
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        min_length=32 if True else 1,  # Dynamic: 32 chars in prod, 1 in dev
        description="Application secret key (change in production)"
    )
    jwt_secret: str = Field(
        default="dev-jwt-secret-change-in-production",
        min_length=32 if True else 1,  # Dynamic: 32 chars in prod, 1 in dev
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
        description="Allowed CORS origins"
    )

    # ── Integrations ─────────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic Claude API key (optional)"
    )

    # ── Deployment ───────────────────────────────────────────────────────────
    deployment_id: str = Field(
        default="dev-local",
        description="Deployment identifier for logging"
    )

    class Config:
        """Pydantic v2 configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, v: str, info) -> str:
        """Ensure database URL is provided and uses async driver.
        
        In production, DATABASE_URL is required. Development allows empty string
        for local SQLite fallback (if configured).
        """
        # Empty string is only allowed in development
        if not v:
            environment = info.data.get("environment", "development")
            if environment == "production":
                raise ValueError(
                    "database_url is required in production. "
                    "Set DATABASE_URL environment variable with format: "
                    "postgresql+asyncpg://user:password@host:port/database"
                )
            # Development: empty is OK (allows fallback)
            logger.warning("database_url not provided; development fallback may be used")
            return v
        
        # If provided, validate async driver
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "database_url must use postgresql+asyncpg:// (async) driver. "
                f"Got: {v[:50]}..."
            )
        return v

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def validate_origins(cls, v: list[str], info) -> list[str]:
        """Reject wildcard origins in production."""
        if "*" in v:
            environment = info.data.get("environment", "development")
            if environment == "production":
                raise ValueError(
                    "Wildcard CORS origins (*) not allowed in production. "
                    f"Provide explicit origins: {v}"
                )
            logger.warning("Wildcard CORS origin (*) used in non-production environment")
        return v

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Ensure secret key meets production standards."""
        environment = info.data.get("environment", "development")
        if environment == "production" and (not v or len(v) < 32):
            raise ValueError(
                "secret_key must be at least 32 characters in production. "
                "Generate with: openssl rand -hex 32"
            )
        if environment == "production" and v.startswith("dev-"):
            logger.error("Production environment using development secret key (dev-*)")
            raise ValueError("Production secret_key cannot start with 'dev-'")
        return v

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """Ensure JWT secret meets production standards."""
        environment = info.data.get("environment", "development")
        if environment == "production" and (not v or len(v) < 32):
            raise ValueError(
                "jwt_secret must be at least 32 characters in production. "
                "Generate with: openssl rand -hex 32"
            )
        if environment == "production" and v.startswith("dev-"):
            logger.error("Production environment using development JWT secret (dev-*)")
            raise ValueError("Production jwt_secret cannot start with 'dev-'")
        return v


def get_settings() -> Settings:
    """Factory to get validated settings singleton.
    
    Raises ValidationError if any required var is missing or invalid.
    """
    try:
        settings = Settings()
        
        # Log startup config (never secrets)
        logger.info(
            "Config loaded: environment=%s, api=%s:%s, db_pool=%s/%s, jwt_expiry_access=%ds",
            settings.environment,
            settings.api_host,
            settings.api_port,
            settings.database_pool_size,
            settings.database_max_overflow,
            settings.jwt_access_token_expiry,
        )
        
        # Warn if using development defaults in production
        if settings.environment == "production":
            if settings.secret_key.startswith("dev-") or settings.jwt_secret.startswith("dev-"):
                logger.critical("Production environment detected with development secrets!")
                raise ValueError("Cannot start production with development secret defaults")
        
        return settings
    except ValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        raise


# Singleton instance — loaded at module import
settings = get_settings()
---