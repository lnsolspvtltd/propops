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
        gt=0,
        le=100,
        description="SQLAlchemy connection pool size (concurrent connections per worker)"
    )
    database_max_overflow: int = Field(
        default=10,
        ge=0,
        le=100,
        description="SQLAlchemy max overflow (burst connections above pool_size)"
    )
    database_echo: bool = Field(
        default=False,
        description="Log all SQL statements to logger (development only, never in production)"
    )

    # ── API ──────────────────────────────────────────────────────────────────
    api_host: str = Field(
        default="0.0.0.0",
        description="API server bind address (0.0.0.0 for all interfaces)"
    )
    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="API server port"
    )
    api_url: str = Field(
        default="http://localhost:8000",
        description="Public API URL (for webhooks, email links, external references). "
                    "Must match deployment URL in production."
    )

    # ── Anthropic Claude ─────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude LLM integration. "
                    "Get from https://console.anthropic.com/account/keys. "
                    "REQUIRED in production."
    )
    anthropic_default_model: str = Field(
        default="claude-haiku-4-5",
        pattern="^(claude-opus-4-1|claude-sonnet-4|claude-haiku-4-5)$",
        description="Default Claude model for incident analysis (haiku=fast/cheap, opus=most capable)"
    )

    # ── Incident Analysis ────────────────────────────────────────────────────
    incident_max_chars_for_llm: int = Field(
        default=3000,
        gt=100,
        le=10000,
        description="Max characters of incident description to send to Claude (truncate longer)"
    )
    incident_auto_resolve_hours: int = Field(
        default=72,
        ge=0,
        description="Auto-resolve open incidents after this many hours (0 to disable)"
    )

    # ── Email ────────────────────────────────────────────────────────────────
    email_provider: str = Field(
        default="smtp",
        pattern="^(smtp|sendgrid)$",
        description="Email provider: smtp or sendgrid"
    )
    smtp_host: Optional[str] = Field(
        default="localhost",
        description="SMTP server hostname (if email_provider=smtp)"
    )
    smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
        description="SMTP server port (if email_provider=smtp)"
    )
    smtp_username: Optional[str] = Field(
        default=None,
        description="SMTP username (optional for open relay)"
    )
    smtp_password: Optional[str] = Field(
        default=None,
        description="SMTP password (optional for open relay). "
                    "SECURITY-REVIEW: Use app-specific password, never personal account password."
    )
    sendgrid_api_key: Optional[str] = Field(
        default=None,
        description="SendGrid API key (if email_provider=sendgrid). "
                    "Get from https://app.sendgrid.com/settings/api_keys"
    )
    notification_from_email: str = Field(
        default="noreply@propops.app",
        description="From email address for all outgoing notifications"
    )

    # ── Slack ────────────────────────────────────────────────────────────────
    slack_webhook_url: Optional[str] = Field(
        default=None,
        description="Slack webhook URL for incident notifications. "
                    "Get from Slack workspace Settings → Integrations → Incoming Webhooks. "
                    "Leave blank to disable."
    )
    slack_channel: Optional[str] = Field(
        default=None,
        description="Slack channel for alerts (e.g., #incidents). Overrides webhook default."
    )

    # ── Testing ──────────────────────────────────────────────────────────────
    testing: bool = Field(
        default=False,
        description="Enable test mode (test fixtures, mock data). NEVER in production."
    )
    test_database_url: Optional[str] = Field(
        default=None,
        description="Database URL for integration tests (leave blank for in-memory SQLite)"
    )

    # ── Secrets ──────────────────────────────────────────────────────────────
    jwt_secret_key: Optional[str] = Field(
        default=None,
        description="JWT secret key for signing authentication tokens. "
                    "Generate: python -c \"import secrets; print(secrets.token_urlsafe(32))\" "
                    "REQUIRED in production; weak defaults (dev-) are rejected."
    )
    jwt_expiry_seconds: int = Field(
        default=900,
        gt=0,
        le=86400,
        description="JWT access token expiry (seconds, default 15 minutes)"
    )
    refresh_token_expiry_days: int = Field(
        default=7,
        gt=0,
        le=365,
        description="Refresh token expiry (days, default 7 days)"
    )

    # ── Observability ────────────────────────────────────────────────────────
    sentry_dsn: Optional[str] = Field(
        default=None,
        description="Sentry error tracking DSN. Leave blank to disable. "
                    "Get from https://sentry.io/projects/"
    )
    datadog_enabled: bool = Field(
        default=False,
        description="Enable DataDog APM (requires DataDog agent in container)"
    )

    # ── Development & Debug ──────────────────────────────────────────────────
    verbose_http_logging: bool = Field(
        default=False,
        description="Log all HTTP requests and responses. NEVER in production."
    )
    reload_on_change: bool = Field(
        default=False,
        description="Reload on file change (uvicorn --reload). Development only."
    )
    profiling_enabled: bool = Field(
        default=False,
        description="Enable cProfile output. Development only."
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Validators
    # ─────────────────────────────────────────────────────────────────────────

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure DATABASE_URL is set explicitly (no production default)."""
        if not v:
            raise ValueError(
                "DATABASE_URL is required. Set explicitly in .env or deployment platform. "
                "Format: postgresql+asyncpg://user:password@host:port/db"
            )
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use asyncpg driver: postgresql+asyncpg://... "
                "(not psycopg2 or standard postgresql://)"
            )
        return v

    @field_validator("anthropic_api_key", mode="after")
    @classmethod
    def validate_anthropic_api_key(cls, v: Optional[str], info) -> Optional[str]:
        """Reject weak API keys in production."""
        environment = info.data.get("environment", "development")
        if not v:
            if environment == "production":
                raise ValueError(
                    "ANTHROPIC_API_KEY is required in production. "
                    "Get from https://console.anthropic.com/account/keys"
                )
            logger.warning("ANTHROPIC_API_KEY not set; Claude integration disabled")
            return None
        
        if v.startswith("dev-") and environment == "production":
            raise ValueError(
                "ANTHROPIC_API_KEY has weak 'dev-' prefix in production environment. "
                "Use strong random key from https://console.anthropic.com/account/keys"
            )
        return v

    @field_validator("jwt_secret_key", mode="after")
    @classmethod
    def validate_jwt_secret_key(cls, v: Optional[str], info) -> Optional[str]:
        """Reject weak JWT secrets in production."""
        environment = info.data.get("environment", "development")
        if not v:
            if environment == "production":
                raise ValueError(
                    "JWT_SECRET_KEY is required in production. "
                    "Generate: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            logger.warning("JWT_SECRET_KEY not set; using insecure default for development only")
            return "dev-insecure-key-change-in-production"
        
        if v.startswith("dev-") and environment == "production":
            raise ValueError(
                "JWT_SECRET_KEY has weak 'dev-' prefix in production environment. "
                "Generate strong random key: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        
        if len(v) < 32 and environment in ("staging", "production"):
            raise ValueError(
                f"JWT_SECRET_KEY must be ≥32 characters in {environment} (got {len(v)}). "
                "Generate: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        return v

    @field_validator("debug", mode="after")
    @classmethod
    def validate_debug(cls, v: bool, info) -> bool:
        """Reject debug=true in production."""
        environment = info.data.get("environment", "development")
        if v and environment == "production":
            raise ValueError("DEBUG must be false in production (security risk)")
        return v

    @field_validator("email_provider", mode="after")
    @classmethod
    def validate_email_provider(cls, v: str, info) -> str:
        """Validate email provider and ensure required fields are set."""
        if v == "smtp":
            smtp_host = info.data.get("smtp_host")
            if not smtp_host:
                raise ValueError("SMTP_HOST required when EMAIL_PROVIDER=smtp")
        elif v == "sendgrid":
            sendgrid_key = info.data.get("sendgrid_api_key")
            if not sendgrid_key:
                raise ValueError("SENDGRID_API_KEY required when EMAIL_PROVIDER=sendgrid")
        return v

    # ─────────────────────────────────────────────────────────────────────────
    # Computed Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"

    @property
    def database_engine_kwargs(self) -> dict:
        """SQLAlchemy async engine kwargs (pooling, echo, etc.)."""
        return {
            "poolclass": "AsyncPool",  # Use async connection pool
            "pool_size": self.database_pool_size,
            "max_overflow": self.database_max_overflow,
            "echo": self.database_echo,
            "echo_pool": self.database_echo,
            "connect_args": {
                "timeout": 30,  # Connection timeout (seconds)
                "command_timeout": 60,  # Query timeout (seconds)
                "server_settings": {
                    "jit": "off",  # Disable JIT for query consistency
                }
            }
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings (cached singleton).
    
    Returns:
        Settings: Singleton Settings instance with validated configuration.
    
    Raises:
        ValidationError: If any required setting is missing or invalid.
        ValueError: If weak secrets detected in production.
    
    Usage:
        from backend.core.config import get_settings
        settings = get_settings()
        print(settings.database_url)
    
    Testing:
        @pytest.fixture(autouse=True)
        def reset_settings():
            get_settings.cache_clear()
            yield
            get_settings.cache_clear()
    
    SECURITY-REVIEW: This function is called exactly once at app startup to ensure
    all configuration is validated immediately and consistently. Subsequent calls
    return cached singleton, avoiding repeated validation overhead.
    """
    try:
        settings = Settings()
        logger.info(
            f"Settings loaded: environment={settings.environment}, "
            f"debug={settings.debug}, api_url={settings.api_url}"
        )
        return settings
    except ValidationError as e:
        logger.critical(f"Configuration validation failed: {e}")
        raise
    except Exception as e:
        logger.critical(f"Unexpected error loading settings: {e}", exc_info=True)
        raise
