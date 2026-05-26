"""Tests for backend.core.config module."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.core.config import Settings, get_settings, validate_startup_settings


class TestSettingsValidation:
    """Test Settings class validation."""

    def test_default_settings_load(self):
        """Test that Settings loads with minimal config."""
        get_settings.cache_clear()
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            settings = get_settings()
            assert settings.environment == "development"
            assert settings.is_production is False

    def test_production_environment_detection(self):
        """Test is_production property."""
        get_settings.cache_clear()
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            settings = get_settings()
            assert settings.is_production is True

    def test_database_url_required_in_production(self):
        """Test that DATABASE_URL is enforced in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(environment="production", database_url=None)
        assert "DATABASE_URL" in str(exc_info.value)

    def test_database_url_optional_in_development(self):
        """Test that DATABASE_URL is optional in development."""
        settings = Settings(environment="development", database_url=None)
        assert settings.database_url is None

    def test_secret_key_length_enforced_in_production(self):
        """Test that SECRET_KEY must be ≥32 chars in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(environment="production", secret_key="short-key")
        assert "32 characters" in str(exc_info.value)

    def test_secret_key_placeholder_rejected_in_production(self):
        """Test that placeholder values are rejected in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(environment="production", secret_key="change-me-to-secure-random-value")
        assert "placeholder" in str(exc_info.value).lower()

    def test_secret_key_accepted_in_development(self):
        """Test that placeholder values are accepted in development."""
        settings = Settings(environment="development", secret_key="change-me-in-prod")
        assert settings.secret_key == "change-me-in-prod"

    def test_cors_origins_parse_comma_separated_string(self):
        """Test that CORS_ORIGINS parses comma-separated string."""
        settings = Settings(cors_origins="http://localhost:3000, https://app.example.com")
        assert settings.cors_origins == ["http://localhost:3000", "https://app.example.com"]

    def test_cors_origins_accept_list(self):
        """Test that CORS_ORIGINS accepts list directly."""
        origins = ["http://localhost:3000", "https://app.example.com"]
        settings = Settings(cors_origins=origins)
        assert settings.cors_origins == origins

    def test_imap_port_validation(self):
        """Test that IMAP_PORT must be valid port range."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(imap_port=99999)
        assert "less than or equal to 65535" in str(exc_info.value)

    def test_smtp_port_validation(self):
        """Test that SMTP_PORT must be valid port range."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(smtp_port=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    def test_log_level_validation(self):
        """Test that LOG_LEVEL must be valid."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(log_level="INVALID")
        assert "string should match pattern" in str(exc_info.value)

    def test_log_level_valid_values(self):
        """Test all valid LOG_LEVEL values."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            settings = Settings(log_level=level)
            assert settings.log_level == level


class TestSettingsCaching:
    """Test get_settings() caching behavior."""

    def test_get_settings_returns_singleton(self):
        """Test that get_settings returns same instance."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_cache_clear_creates_new_instance(self):
        """Test that cache_clear creates new instance on next call."""
        settings1 = get_settings()
        get_settings.cache_clear()
        settings2 = get_settings()
        assert settings1 is not settings2


class TestValidateStartupSettings:
    """Test validate_startup_settings function."""

    def test_production_validation_passes_with_valid_config(self):
        """Test that validation passes in production with all required settings."""
        get_settings.cache_clear()
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@host:5432/db",
                "SECRET_KEY": "a" * 32,
            },
        ):
            # Should not raise
            validate_startup_settings()

    def test_production_validation_fails_without_database_url(self):
        """Test that validation fails in production without DATABASE_URL."""
        get_settings.cache_clear()
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DATABASE_URL": "",
                "SECRET_KEY": "a" * 32,
            },
        ):
            with pytest.raises(SystemExit):
                validate_startup_settings()

    def test_development_validation_passes_with_minimal_config(self):
        """Test that validation passes in development with minimal config."""
        get_settings.cache_clear()
        with patch.dict(os.environ, {"ENVIRONMENT": "development"}):
            # Should not raise
            validate_startup_settings()
---