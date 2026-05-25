"""Application configuration from environment variables."""
from functools import lru_cache
from typing import Optional
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    secret_key: str = ""
    cors_origins: list[str] = ["http://localhost:3000"]

    @field_validator("secret_key", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        """
        SECURITY-REVIEW: Enforce non-empty secret_key in production.
        Empty secret_key renders session/JWT security ineffective.
        """
        environment = info.data.get("environment", "development")
        if environment == "production" and not v:
            raise ValueError(
                "secret_key must be set via SECRET_KEY environment variable in production"
            )
        if environment == "development" and not v:
            import logging
            logging.getLogger(__name__).warning(
                "⚠️ CRITICAL: secret_key is empty in development. "
                "Set SECRET_KEY in .env for security testing. "
                "Production deployment will fail without this."
            )
        return v

    @model_validator(mode='after')
    def validate_production_secrets(self) -> 'Settings':
        """Raise if required secrets are missing in production."""
        if self.environment == 'production':
            if not self.secret_key:
                raise ValueError("SECRET_KEY must be set in production environment")
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY must be set in production environment")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
---