"""Tests for backend.core.config settings and validation.

Tests validate:
- Production environment enforces strong secrets and required settings
- Development environment allows weak defaults for local testing
- Validators produce clear, actionable error messages

Run: pytest tests/test_config.py -v
"""
import pytest
from pydantic import ValidationError

from backend.core.config import Settings, get_settings


class TestSettingsValidation:
    """Test configuration validation rules.

    Error message assertions match the exact strings raised by validators
    in backend/core/config.py. Update these if validator messages change.
    """

    # ── database_url ────────────────────────────────────────────────────────

    def test_database_url_required_in_production(self):
        """database_url must be set in production; None triggers ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url=None,
                secret_key="a-strong-production-secret-key-123456789",
                jwt_secret="a-strong-production-jwt-secret-123456789",
            )
        assert "database_url must be set explicitly in production" in str(exc_info.value)

    def test_database_url_optional_in_development(self):
        """database_url may be None in development without raising an error."""
        s = Settings(environment="development", database_url=None)
        assert s.database_url is None

    # ── debug ────────────────────────────────────────────────────────────────

    def test_debug_false_required_in_production(self):
        """debug=True must raise ValidationError in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                debug=True,
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="a-strong-production-secret-key-123456789",
                jwt_secret="a-strong-production-jwt-secret-123456789",
            )
        assert "debug must be False in production environment" in str(exc_info.value)

    def test_debug_allowed_in_development(self):
        """debug=True is permitted in development."""
        s = Settings(environment="development", debug=True)
        assert s.debug is True

    # ── secret_key ──────────────────────────────────────────────────────────

    def test_secret_key_must_be_strong_in_production(self):
        """secret_key shorter than 32 chars raises ValidationError in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="short",
                jwt_secret="a-strong-production-jwt-secret-123456789",
            )
        assert "secret_key must be 32+ characters" in str(exc_info.value)

    def test_secret_key_cannot_use_dev_prefix_in_production(self):
        """secret_key starting with 'dev-' raises ValidationError in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="dev-secret-key-change-in-production-padded-to-32",
                jwt_secret="a-strong-production-jwt-secret-123456789",
            )
        assert "NOT start with 'dev-'" in str(exc_info.value)

    def test_secret_key_allowed_in_development(self):
        """Development secret key defaults are accepted in development."""
        s = Settings(environment="development", secret_key="dev-secret-key-local-testing-only")
        assert s.secret_key == "dev-secret-key-local-testing-only"

    # ── jwt_secret ──────────────────────────────────────────────────────────

    def test_jwt_secret_must_be_strong_in_production(self):
        """jwt_secret shorter than 32 chars raises ValidationError in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="a-strong-production-secret-key-123456789",
                jwt_secret="short",
            )
        assert "jwt_secret must be 32+ characters" in str(exc_info.value)

    def test_jwt_secret_cannot_use_dev_prefix_in_production(self):
        """jwt_secret starting with 'dev-' raises ValidationError in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="a-strong-production-secret-key-123456789",
                jwt_secret="dev-jwt-secret-change-in-production-padded-to-32",
            )
        assert "NOT start with 'dev-'" in str(exc_info.value)

    def test_jwt_secret_allowed_in_development(self):
        """Development JWT secret defaults are accepted in development."""
        s = Settings(environment="development", jwt_secret="dev-jwt-secret-local-testing-only")
        assert s.jwt_secret == "dev-jwt-secret-local-testing-only"

    # ── allowed_origins ─────────────────────────────────────────────────────

    def test_allowed_origins_cannot_use_wildcard_in_production(self):
        """CORS wildcard * raises ValidationError in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(
                environment="production",
                database_url="postgresql+asyncpg://user:pass@localhost/db",
                secret_key="a-strong-production-secret-key-123456789",
                jwt_secret="a-strong-production-jwt-secret-123456789",
                allowed_origins=["*"],
            )
        assert "allowed_origins must NOT contain '*'" in str(exc_info.value)

    def test_allowed_origins_wildcard_allowed_in_development(self):
        """CORS wildcard is permitted in development for local convenience."""
        s = Settings(environment="development", allowed_origins=["*"])
        assert "*" in s.allowed_origins

    def test_allowed_origins_multiple_explicit_origins_in_production(self):
        """Multiple explicit origins are accepted in production (no wildcard)."""
        s = Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@localhost/db",
            secret_key="a-strong-production-secret-key-123456789",
            jwt_secret="a-strong-production-jwt-secret-123456789",
            allowed_origins=["https://example.com", "https://app.example.com"],
        )
        assert "https://example.com" in s.allowed_origins

    # ── get_settings singleton ───────────────────────────────────────────────

    def test_get_settings_returns_singleton(self, reset_settings_cache, monkeypatch):
        """get_settings() returns the same instance on repeated calls."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2

    def test_get_settings_cache_clear_returns_new_instance(self, monkeypatch):
        """After cache_clear(), get_settings() returns a fresh instance."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        get_settings.cache_clear()
        s1 = get_settings()
        get_settings.cache_clear()
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        s2 = get_settings()
        assert s1 is not s2
