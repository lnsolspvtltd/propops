"""Application configuration via environment variables.

Pydantic v2 Settings with full validation. All config loaded from .env at startup.

Key design decisions:
- get_settings() uses @lru_cache so Settings is instantiated once per process.
  Call get_settings.cache_clear() in tests to reset between test cases.
- All secrets are Optional at definition time; validators enforce requirements
  in production so development can run without all secrets configured.
- is_production property for environment-specific guards throughout the codebase.
"""

import logging
import sys
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
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

    # ── Core ──────────────────────────────────────────────────────────────────
    environment: str = Field(
        default="development",
        description="Deployment environment: development | staging | production",
    )
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
    debug: bool = Field(default=False)

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL async URL (postgresql+asyncpg://...). Required in production.",
    )

    # ── IMAP inbox polling ────────────────────────────────────────────────────
    imap_host: str = Field(default="imap.gmail.com")
    imap_port: int = Field(default=993, ge=1, le=65535)
    imap_username: str = Field(default="")
    imap_password: str = Field(default="")
    imap_poll_interval_seconds: int = Field(default=60, ge=10, le=3600)

    # ── SMTP outbound ─────────────────────────────────────────────────────────
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")

    # ── AI ────────────────────────────────────────────────────────────────────
    anthropic_api_key: Optional[str] = Field(default=None)

    # ── Twilio (Phase 2) ──────────────────────────────────────────────────────
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_phone_number: str = Field(default="")

    # ── Security ──────────────────────────────────────────────────────────────
    # SECURITY-REVIEW: SECRET_KEY validation enforces production safety
    secret_key: str = Field(
        default="dev-secret-key-local-testing-only",
        description=(
            "Cryptographic key for signing sessions and tokens. "
            "Must be ≥32 characters in production. "
            "Generate with: openssl rand -hex 32"
        ),
    )

    # ── CORS & HTTP ───────────────────────────────────────────────────────────
    cors_origins: List[str] = Field(
        default=["http://localhost:3000"],
        description=(
            "Comma-separated or list of allowed CORS origins. "
            "Examples: ['http://localhost:3000'] (dev), "
            "['https://app.propops.io', 'https://www.propops.io'] (prod)"
        ),
    )

    # ── Organization ──────────────────────────────────────────────────────────
    default_org_id: Optional[str] = Field(
        default=None,
        description=(
            "UUID of default organization for email polling. "
            "In multi-tenant setup, should be per-org; for now defaults to first org."
        ),
    )

    # ── Computed Properties ───────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        """True if running in production environment."""
        return self.environment.lower() == "production"

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """Enforce DATABASE_URL in production."""
        environment = info.data.get("environment", "").lower()
        if environment == "production" and not v:
            raise ValueError(
                "DATABASE_URL is required in production. "
                "Set DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db"
            )
        return v

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Enforce SECRET_KEY strength in production."""
        environment = info.data.get("environment", "").lower()
        if environment == "production":
            if len(v) < 32:
                raise ValueError(
                    f"SECRET_KEY must be ≥32 characters in production (got {len(v)}). "
                    f"Generate with: openssl rand -hex 32"
                )
            if v == "dev-secret-key-local-testing-only" or v.startswith("change-me"):
                raise ValueError(
                    "SECRET_KEY is a placeholder value. "
                    "Generate a random key: openssl rand -hex 32"
                )
        return v

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_anthropic_api_key(cls, v: Optional[str], info) -> Optional[str]:
        """Warn if Anthropic API key missing in production."""
        environment = info.data.get("environment", "").lower()
        if environment == "production" and not v:
            logger.warning(
                "ANTHROPIC_API_KEY not set in production. "
                "AI features (incident triage) will be unavailable."
            )
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v) -> List[str]:
        """Parse comma-separated CORS_ORIGINS string or accept list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v if isinstance(v, list) else []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached Settings instance.

    Returns:
        Settings singleton (cached per process).

    Raises:
        ValidationError: If any required setting is invalid.

    Examples:
        >>> settings = get_settings()
        >>> print(settings.database_url)

        >>> # In tests, reset the cache:
        >>> get_settings.cache_clear()
        >>> settings = get_settings()  # Fresh instance
    """
    return Settings()


def validate_startup_settings() -> None:
    """Validate all critical settings on startup.

    Raises:
        SystemExit: If any critical setting is invalid in production.
    """
    settings = get_settings()

    if settings.is_production:
        errors = []

        if not settings.database_url:
            errors.append("DATABASE_URL is required in production")

        if len(settings.secret_key) < 32:
            errors.append("SECRET_KEY must be ≥32 characters in production")

        if errors:
            logger.critical(
                "Configuration validation failed in production:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )
            sys.exit(1)

        logger.info("Production settings validated successfully")
---