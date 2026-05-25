"""Configuration and settings for PropOps backend."""
import logging
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str

    # IMAP
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str
    imap_poll_interval_seconds: int = 60

    # SMTP
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str

    # AI
    anthropic_api_key: str

    # Twilio (Phase 2)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_phone_number: str = ""

    # Security
    secret_key: str
    cors_origins: List[str] = ["http://localhost:3000"]
    
    # Organization
    default_org_id: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **data):
        """Initialize settings with custom CORS parsing.
        
        Parses CORS_ORIGINS from environment:
          - If it looks like JSON: [\"...\", \"...\"], parse as JSON list
          - If it's comma-separated: a,b,c, split on comma and strip whitespace
          - Default: [\"http://localhost:3000\"]
        """
        super().__init__(**data)
        
        # Validate SECRET_KEY strength
        if self.secret_key == "change-me-to-secure-random-value-with-openssl-rand-hex-32":
            raise ValueError(
                "SECRET_KEY must be changed from default placeholder. "
                "Generate with: openssl rand -hex 32"
            )
        
        if len(self.secret_key) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters (64 hex digits). "
                "Generate with: openssl rand -hex 32"
            )


settings = Settings()
---