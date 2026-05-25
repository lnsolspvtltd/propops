"""Tests for backend.core.config settings and validation."""
import pytest
from pydantic import ValidationError
from backend.core.config import Settings


class TestSettingsValidation:
    """Test configuration validation rules."""

    def test_database_url_required_in_production(self):
        """Test that database_url is required in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="",
                secret_key="dev-secret-key-change-in-production" * 2,
                jwt_secret="dev-jwt-secret-change-in-production" * 2,
            )
        assert "database_url must be explicitly configured in production" in str(exc_info.value)

    def test_database_url_optional_in_development(self):
        """Test that database_url is optional in development."""
        settings = Settings(environment="development", database_url="")
        assert settings.database_url == ""

    def test_debug_false_required_in_production(self):
        """Test that debug must be False in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                debug=True,
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="a" * 32,
                jwt_secret="b" * 32,
            )
        assert "debug=True is not allowed in production" in str(exc_info.value)

    def test_debug_allowed_in_development(self):
        """Test that debug can be True in development."""
        settings = Settings(
            environment="development",
            debug=True,
        )
        assert settings.debug is True

    def test_secret_key_minimum_length_in_production(self):
        """Test that secret_key must be 32+ chars in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="short-key",
                jwt_secret="b" * 32,
            )
        assert "secret_key must be at least 32 characters in production" in str(exc_info.value)

    def test_secret_key_cannot_be_dev_default_in_production(self):
        """Test that secret_key cannot use 'dev-' prefix in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="dev-secret-key-change-in-production" * 2,
                jwt_secret="b" * 32,
            )
        assert "secret_key in production must not use development defaults" in str(exc_info.value)

    def test_secret_key_allowed_in_development(self):
        """Test that development secret key defaults work in development."""
        settings = Settings(
            environment="development",
            secret_key="dev-secret-key-change-in-production",
        )
        assert settings.secret_key == "dev-secret-key-change-in-production"

    def test_jwt_secret_minimum_length_in_production(self):
        """Test that jwt_secret must be 32+ chars in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="a" * 32,
                jwt_secret="short-key",
            )
        assert "jwt_secret must be at least 32 characters in production" in str(exc_info.value)

    def test_jwt_secret_cannot_be_dev_default_in_production(self):
        """Test that jwt_secret cannot use 'dev-' prefix in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="a" * 32,
                jwt_secret="dev-jwt-secret-change-in-production" * 2,
            )
        assert "jwt_secret in production must not use development defaults" in str(exc_info.value)

    def test_jwt_secret_allowed_in_development(self):
        """Test that development JWT secret defaults work in development."""
        settings = Settings(
            environment="development",
            jwt_secret="dev-jwt-secret-change-in-production",
        )
        assert settings.jwt_secret == "dev-jwt-secret-change-in-production"

    def test_allowed_origins_cannot_use_wildcard_in_production(self):
        """Test that CORS origins cannot use wildcard in production."""
        with pytest.raises(ValidationError) as exc_info: