"""Application configuration from environment variables."""
from functools import lru_cache
from typing import Optional
from pydantic import field_validator
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

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
---