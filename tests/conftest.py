"""Pytest configuration and shared fixtures for PropOps backend tests.

This module provides:
- Settings singleton reset between tests (prevents test pollution)
- Mock async database session for unit tests
- Test settings fixture with safe development defaults
- Test database URL for integration tests

All async fixtures require pytest-asyncio (configured via pytest.ini or pyproject.toml).
"""
import os

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Reset settings singleton cache before and after every test.

    Ensures each test starts with a clean settings instance, preventing
    environment variable changes in one test from leaking into others.

    Usage: This fixture is autouse=True — no explicit usage required.
    It runs automatically for every test in the suite.

    Example of explicit usage (when you need the cache reset at a specific point):
        def test_something(reset_settings_cache):
            os.environ["ENVIRONMENT"] = "production"
            get_settings.cache_clear()  # manual reset if needed mid-test
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_settings(monkeypatch):
    """Provide settings with safe development defaults for unit tests.

    Sets environment variables via monkeypatch (automatically restored after test).
    Resets the settings singleton cache so the test gets a fresh instance.

    Args:
        monkeypatch: pytest monkeypatch fixture

    Returns:
        Settings instance configured for development testing.

    Example::

        def test_something(test_settings):
            assert test_settings.environment == "development"
    """
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/propops_test")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-key-local-testing-only")
    monkeypatch.setenv("JWT_SECRET", "dev-jwt-secret-local-testing-only")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()
    s = get_settings()
    yield s
    get_settings.cache_clear()


@pytest.fixture
def mock_db_session():
    """Provide a mock async database session for unit tests.

    Use this when testing business logic that calls the database, but you
    don't want to require a real PostgreSQL connection.

    Returns:
        AsyncMock(spec=AsyncSession) with all common methods mocked.

    Example::

        async def test_create_incident(mock_db_session):
            await create_incident(db=mock_db_session, ...)
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_awaited_once()
    """
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.scalar_one_or_none = AsyncMock(return_value=None)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    # Context manager support
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.fixture(scope="session")
def test_db_url():
    """Return test database URL for integration tests.

    Uses DATABASE_URL_TEST env var if set (CI environments), otherwise
    falls back to a local test PostgreSQL database.

    Tests that use this fixture require a real PostgreSQL instance.
    Use mock_db_session for unit tests that should not need a database.

    Returns:
        str: asyncpg-compatible PostgreSQL connection string.
    """
    return os.getenv(
        "DATABASE_URL_TEST",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/propops_test",
    )
