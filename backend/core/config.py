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
        description="Application secret key (change in production)"
    )
    jwt_secret: str = Field(
        default="dev-jwt-secret-change-in-production",
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
    def validate_database_url(cls, value: str, info) -> str:
        """Validate that database_url is non-empty in production.
        
        In development, empty DATABASE_URL is allowed (for local testing),
        but in production it must be explicitly configured.
        
        Args:
            value: The database URL from environment
            info: ValidationInfo with context
            
        Returns:
            Validated database URL
            
        Raises:
            ValueError: If empty in production environment
        """
        environment = info.data.get("environment", "development")
        if environment == "production" and not value:
            raise ValueError(
                "database_url must be explicitly configured in production. "
                "Set DATABASE_URL environment variable with format: "
                "postgresql+asyncpg://user:password@host:port/database"
            )
        if not value and environment != "production":
            logger.warning(
                "database_url is empty in %s environment. "
                "Application will fail at runtime if database operations are attempted.",
                environment
            )
        return value

    @field_validator("debug", mode="after")
    @classmethod
    def validate_debug_mode(cls, value: bool, info) -> bool:
        """Validate that debug mode is disabled in production.
        
        Args:
            value: The debug flag
            info: ValidationInfo with context
            
        Returns:
            Validated debug flag
            
        Raises:
            ValueError: If debug=True in production
        """
        environment = info.data.get("environment", "development")
        if value and environment == "production":
            raise ValueError(
                "debug=True is not allowed in production environment. "
                "Set DEBUG=false in production configuration."
            )
        if value:
            logger.warning(
                "DEBUG mode enabled in %s environment. "
                "This exposes sensitive information and should never be enabled in production.",
                environment
            )
        return value

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, value: str, info) -> str:
        """Validate secret key meets minimum security requirements.
        
        In production, requires 32+ characters.
        In development, allows weak keys for testing.
        
        Args:
            value: The secret key
            info: ValidationInfo with context
            
        Returns:
            Validated secret key
            
        Raises:
            ValueError: If too short in production
        """
        environment = info.data.get("environment", "development")
        if environment == "production" and len(value) < 32:
            raise ValueError(
                "secret_key must be at least 32 characters in production. "
                "Generate with: openssl rand -hex 32"
            )
        if environment == "production" and value.startswith("dev-"):
            raise ValueError(
                "secret_key in production must not use development defaults. "
                "Generate a strong secret: openssl rand -hex 32"
            )
        return value

    @field_validator("jwt_secret", mode="after")
    @classmethod
    def validate_jwt_secret(cls, value: str, info) -> str:
        """Validate JWT secret meets minimum security requirements.
        
        In production, requires 32+ characters and must not be a development default.
        
        Args:
            value: The JWT secret
            info: ValidationInfo with context
            
        Returns:
            Validated JWT secret
            
        Raises:
            ValueError: If too short or using development default in production
        """
        environment = info.data.get("environment", "development")
        if environment == "production" and len(value) < 32:
            raise ValueError(
                "jwt_secret must be at least 32 characters in production. "
                "Generate with: openssl rand -hex 32"
            )
        if environment == "production" and value.startswith("dev-"):
            raise ValueError(
                "jwt_secret in production must not use development defaults. "
                "Generate a strong secret: openssl rand -hex 32"
            )
        return value

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def validate_allowed_origins(cls, value: list[str], info) -> list[str]:
        """Validate CORS origins are properly configured.
        
        In production, ensures wildcard origins are not used.
        
        Args:
            value: List of allowed CORS origins
            info: ValidationInfo with context
            
        Returns:
            Validated list of origins
            
        Raises:
            ValueError: If wildcards used in production
        """
        environment = info.data.get("environment", "development")
        if environment == "production":
            for origin in value:
                if "*" in origin or origin == "*":
                    raise ValueError(
                        "Wildcard CORS origins (*) are not allowed in production. "
                        "Specify explicit origins only: "
                        "https://app.domain.com,https://dashboard.domain.com"
                    )
        return value


def get_settings() -> Settings:
    """Load and validate settings from environment.
    
    Returns:
        Settings: Validated configuration object
        
    Raises:
        ValidationError: If any setting fails validation
    """
    try:
        settings = Settings()
        logger.info(
            f"Settings loaded successfully (environment={settings.environment}, "
            f"debug={settings.debug}, deployment_id={settings.deployment_id})"
        )
        return settings
    except ValidationError as e:
        logger.error(f"Settings validation failed: {e}")
        raise


# Global settings singleton (loaded once at startup)
settings = get_settings()
---