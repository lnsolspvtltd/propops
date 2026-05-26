"""Pytest configuration and shared fixtures for the test suite."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.core.config import get_settings
from backend.core.database import Base


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_settings():
    """Reset settings singleton before each test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def test_db_engine():
    """Create an in-memory SQLite async engine for testing.

    Note: Uses SQLite for simplicity. For real PostgreSQL testing,
    use testcontainers or pytest-postgresql.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine) -> AsyncSession:
    """Provide a test database session."""
    async with AsyncSession(test_db_engine) as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic API client for testing."""
    mock = MagicMock()
    mock.messages.create = MagicMock(
        return_value=MagicMock(
            content=[MagicMock(text='{"urgency": "HIGH", "category": "maintenance"}')]
        )
    )
    return mock


@pytest.fixture
def mock_imap_client():
    """Mock IMAP client for testing email ingestion."""
    mock = AsyncMock()
    mock.login = AsyncMock()
    mock.select_folder = AsyncMock()
    mock.search = AsyncMock(return_value=[])
    mock.fetch = AsyncMock(return_value={})
    mock.logout = AsyncMock()
    return mock


@pytest.fixture
def mock_smtp_client():
    """Mock SMTP client for testing email sending."""
    mock = AsyncMock()
    mock.login = AsyncMock()
    mock.send_message = AsyncMock()
    mock.quit = AsyncMock()
    return mock
---