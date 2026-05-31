"""Application configuration from environment variables."""
import logging
from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

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

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 7

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/propops"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30

    # AI
    anthropic_api_key: str = ""

    # Email
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_poll_interval_seconds: int = 60
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""

    # Encryption (org credentials)
    fernet_key: str = ""

    # Demo login (development only)
    enable_demo_login: bool = False  # must be explicitly enabled; never on by default
    demo_email: str = "demo@propops.app"
    demo_password: str = "demo"
    demo_org_id: str = "00000000-0000-0000-0000-000000000001"

    # Optional integrations
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""
    pm_contact_email: str = "hello@propops.app"

    @field_validator("secret_key", mode="after")
    @classmethod
    def warn_empty_secret_in_dev(cls, v: str, info) -> str:
        environment = info.data.get("environment", "development")
        if environment == "production" and not v:
            raise ValueError("SECRET_KEY must be set in production")
        if environment == "development" and not v:
            logger.warning("secret_key is empty in development — set SECRET_KEY in .env")
        return v

    @model_validator(mode="after")
    def validate_demo_config(self) -> "Settings":
        if self.enable_demo_login:
            if not self.demo_password:
                raise ValueError("enable_demo_login=True requires DEMO_PASSWORD to be set")
            _weak = {"demo", "password", "admin", "test", "123456", "secret"}
            if self.demo_password.lower() in _weak:
                raise ValueError("DEMO_PASSWORD is too weak — set a strong value in .env")
        return self

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment == "production":
            if not self.secret_key:
                raise ValueError("SECRET_KEY must be set in production")
            if not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY must be set in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
