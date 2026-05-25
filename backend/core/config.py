"""Application configuration from environment variables."""
import logging
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # AI
    anthropic_api_key: str = ""

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/propops"

    # Email ingestion
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_poll_interval_seconds: int = 60

    # SMTP outbound
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""

    # Twilio SMS
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # App
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = ""  # REQUIRED: set SECRET_KEY in environment
    cors_origins: list[str] = ["http://localhost:3000"]

    # SECURITY-REVIEW: JWT config for auth tokens
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    def validate_startup(self) -> None:
        """Validate critical config on startup. Raises ValueError if invalid."""
        # SECURITY-REVIEW: Enforce SECRET_KEY presence and strength
        if not self.secret_key or len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be set in environment and >= 32 characters long. "
                "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
            )
        
        if self.is_production:
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required in production")
            if "localhost" in self.database_url:
                raise ValueError("Cannot use localhost database URL in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_startup()
    return settings


settings = get_settings()

---