"""Pytest configuration and shared fixtures for all tests.

Provides:
- Settings fixture that resets singleton cache between tests
- Mock async database session
- Test AsyncClient for FastAPI integration tests
- Async test marker configuration
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from contextlib import asynccontextmanager

from backend.core.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_