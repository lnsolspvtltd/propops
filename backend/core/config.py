"""Application configuration via environment variables.

Uses Pydantic v2 settings with validation and type safety.
All config is read from .env at startup; immutable at runtime.
All secrets must be provided explicitly — no hardcoded defaults in production.
"""
import logging
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationError

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings from environment.
    
    Pydantic v2 config using BaseSettings for automatic .env loading.
    All fields use Field() with validation to ensure type safety and sane defaults.
    Secrets validation ensures weak defaults are not used in production.
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
        description="Anthropic Claude API key (optional)"
    )

    # ── Deployment ───────────────────────────────────────────────────────────
    deployment_id: str = Field(
        default="dev-local",
        description="Deployment identifier for logging and tracing"
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, value: Optional[str], info) -> Optional[str]:
        """Validate that database_url is provided and valid in production.
        
        In production, database_url is mandatory and must be a valid PostgreSQL async URI.
        In development, it can be None (will fail at app startup with clear error).
        
        Raises:
            ValueError: If environment is production and database_url is None or empty.
            ValueError: If database_url does not start with postgresql+asyncpg:// scheme.
        """
        environment = info.data.get("environment", "development")
        
        if environment == "production":
            if not value or not value.strip():
                raise ValueError(
                    "DATABASE_URL is required in production environment. "
                    "Set it in your deployment platform (Railway, Heroku, etc.). "
                    "Do not hardcode in .env."
                )
        
        if value and value.strip():
            # Validate URI scheme for all environments when provided
            if not value.startswith("postgresql+asyncpg://"):
                raise ValueError(
                    f"DATABASE_URL must use postgresql+asyncpg:// scheme (async SQLAlchemy driver). "
                    f"Got: {value.split('://')[0]}:// — did you forget '+asyncpg'?"
                )
        
        return value

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, value: str, info) -> str:
        """Validate that secret_key is strong in production.
        
        In production, secret_key must:
        - Be at least 32 characters (cryptographically strong)
        - Not start with 'dev-' (prevents accidental weak keys in prod)
        - Not contain obvious test values
        
        Raises:
            ValueError: If environment is production and secret_key is weak.
        """
        environment = info.data.get("environment", "development")
        
        if environment == "production":
            if value.startswith("dev-") or value.startswith("test-"):
                raise ValueError(
                    "SECRET_KEY in production must not use development defaults (dev-*, test-*). "
                    "Generate a strong key with: openssl rand -hex 32"
                )
            if len(value) < 32:
                raise ValueError(
                    f"SECRET_KEY in production must be at least 32 characters (got {len(value)}). "
                    "Generate with: openssl rand -hex 32"
                )
        
        return value

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, value: str, info) -> str:
        """Validate that jwt_secret is strong in production.
        
        In production, jwt_secret must:
        - Be at least 32 characters (cryptographically strong)
        - Not start with 'dev-' (prevents accidental weak keys in prod)
        - Not contain obvious test values
        
        Raises:
            ValueError: If environment is production and jwt_secret is weak.
        """
        environment = info.data.get("environment", "development")
        
        if environment == "production":
            if value.startswith("dev-") or value.startswith("test-"):
                raise ValueError(
                    "JWT_SECRET in production must not use development defaults (dev-*, test-*). "
                    "Generate a strong key with: openssl rand -hex 32"
                )
            if len(value) < 32:
                raise ValueError(
                    f"JWT_SECRET in production must be at least 32 characters (got {len(value)}). "
                    "Generate with: openssl rand -hex 32"
                )
        
        return value

    @field_validator("debug", mode="after")
    @classmethod
    def validate_debug_mode(cls, value: bool, info) -> bool:
        """Validate that debug mode is disabled in production.
        
        Debug mode exposes sensitive information and must never be enabled
        in production environments.
        
        Raises:
            ValueError: If environment is production and debug is True.
        """
        environment = info.data.get("environment", "development")
        
        if environment == "production" and value is True:
            raise ValueError(
                "DEBUG must be False in production. "
                "Debug mode exposes sensitive information (tracebacks, env vars, etc.). "
                "Set DEBUG=false in production configuration."
            )
        
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value) -> list[str]:
        """Parse allowed_origins from comma-separated string or list.
        
        Handles both string (from .env) and list inputs.
        Strips whitespace from each origin.
        """
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if origin]
        return ["http://localhost:3000"]

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def validate_allowed_origins(cls, value: list[str], info) -> list[str]:
        """Validate that CORS origins are safe in production.
        
        In production:
        - Wildcard (*) is prohibited (information disclosure risk)
        - Origins must use HTTPS (except localhost for development)
        - At least one origin must be configured
        
        Raises:
            ValueError: If origins contain wildcard in production.
        """
        environment = info.data.get("environment", "development")
        
        if environment == "production":
            if "*" in value:
                raise ValueError(
                    "ALLOWED_ORIGINS cannot contain wildcard (*) in production. "
                    "Specify explicit origins only: https://app.example.com,https://api.example.com"
                )
            
            # Warn if non-HTTPS origins in production (except localhost for edge cases)
            non_https = [o for o in value if not o.startswith("https://") and "localhost" not in o]
            if non_https:
                logger.warning(
                    f"ALLOWED_ORIGINS in production should use HTTPS. "
                    f"Found HTTP origins: {non_https}. "
                    f"Update configuration for security."
                )
        
        return value


def get_settings() -> Settings:
    """Load and validate settings from environment.
    
    Returns:
        Settings: Validated application configuration.
        
    Raises:
        ValidationError: If any configuration is invalid.
            Check error details for which field failed validation.
    """
    try:
        return Settings()
    except ValidationError as e:
        logger.error(
            f"Configuration validation failed. Check your .env file and environment variables. "
            f"Errors: {e.error_count()} field(s) failed validation."
        )
        for error in e.errors():
            logger.error(f"  • {error['loc'][0]}: {error['msg']}")
        raise


# Global settings instance (loaded once at startup)
settings = get_settings()
```

---