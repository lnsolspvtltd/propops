"""Application configuration via environment variables.

Pydantic v2 Settings with full validation. All config loaded from .env at startup.

Key design decisions:
- get_settings() uses @lru_cache so Settings is instantiated once per process.
  Call get_settings.cache_clear() in tests to reset between test cases.
- All secrets are Optional at definition time; validators enforce requirements
  in production so development can run without all secrets configured.
- is_production property for environment-specific guards throughout the codebase.
"""
from functools import lru_cache
from typing import Optional
from pydantic import field_validator
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

    # App
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]
    version: str = "0.1.0-alpha"

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """SECURITY-REVIEW: Ensure secret_key is not empty in production or at all.
        
        Empty secret_key breaks JWT/session signing silently.
        Fail fast at startup rather than runtime.
        """
        if not v or not v.strip():
            env = info.data.get("environment", "development")
            raise ValueError(
                f"secret_key must not be empty. Set SECRET_KEY environment variable. "
                f"(environment={env})"
            )
        return v

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
    secret_key: str = Field(
        default="dev-secret-key-local-testing-only-change-in-production",
        description="Application secret key. Must be 32+ chars in production.",
    )
    cors_origins: List[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins. Never use ['*'] in production.",
    )

    # ── Organisation ─────────────────────────────────────────────────────────
    default_org_id: str = Field(default="")

    # ── Properties ────────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        """True when environment == 'production'."""
        return self.environment == "production"

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v.lower()

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """Reject weak secrets in production."""
        data = info.data
        if data.get("environment") == "production":
            if len(v) < 32 or v.startswith("dev-"):
                raise ValueError(
                    "secret_key must be 32+ characters and NOT start with 'dev-' "
                    "in production. Generate with: openssl rand -hex 32"
                )
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: Optional[str], info) -> Optional[str]:
        """database_url is required in production."""
        data = info.data
        if data.get("environment") == "production" and not v:
            raise ValueError(
                "database_url must be set explicitly in production. "
                "No default is provided."
            )
        return v

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: List[str], info) -> List[str]:
        """Block wildcard CORS in production."""
        data = info.data
        if data.get("environment") == "production" and "*" in v:
            raise ValueError(
                "cors_origins must NOT contain '*' in production. "
                "Use explicit origins."
            )
        return v

    @field_validator("debug")
    @classmethod
    def validate_debug(cls, v: bool, info) -> bool:
        """debug=True is not allowed in production."""
        data = info.data
        if data.get("environment") == "production" and v:
            raise ValueError("debug must be False in production environment")
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the application settings singleton.

    Uses lru_cache so Settings is only instantiated once per process.
    Raises ValidationError at startup if any required setting is invalid.

    For testing, call get_settings.cache_clear() between test cases.
    """
    return Settings()

    Reads from .env file at first call, validates all settings, and caches result.
    Subsequent calls return cached instance.

settings = get_settings()
---