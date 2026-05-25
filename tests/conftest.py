"""Pytest configuration and shared fixtures for PropOps backend tests.

This module provides:
- Database session fixtures (async and sync)
- Settings fixtures with cache reset
- HTTP client fixtures
- Mock/patch utilities

All async fixtures support pytest-asyncio plugin.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import Stat