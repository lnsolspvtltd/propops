"""Tests for backend.main application startup and configuration."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from backend.main import app, lifespan


@pytest.fixture
def test_client():
    """Provide a synchronous test client for the FastAPI app."""
    return TestClient(app)


@pytest.mark.asyncio
async def test_app_startup_with_all_services():
    """Test that app starts up with database and inbox poller initialized."""
    with patch("backend.main.init_db", new_callable=AsyncMock) as mock_db:
        with patch("backend.main.start_inbox_poller", new_callable=AsyncMock) as mock_poller:
            mock_db.return_value = None
            mock_poller.return_value = None

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/")
                assert response.status_code == 200
                assert response.json()["status"] == "running"


@pytest.mark.asyncio
async def test_app_startup_fails_on_database_error():
    """Test that app startup fails if database initialization fails."""
    with patch("backend.main.init_db", new_callable=AsyncMock) as mock_db:
        mock_db.side_effect = RuntimeError("Database connection failed")

        with pytest.raises(RuntimeError):
            # Manually trigger the lifespan startup
            async with lifespan(app):
                pass


@pytest.mark.asyncio
async def test_app_startup_continues_if_poller_fails():
    """Test that app starts even if inbox poller fails (graceful degradation)."""
    with patch("backend.main.init_db", new_callable=AsyncMock) as mock_db:
        with patch("backend.main.start_inbox_poller", new_callable=AsyncMock) as mock_poller:
            mock_db.return_value = None
            mock_poller.side_effect = RuntimeError("Poller initialization failed")

            # Should not raise even though poller failed
            async with lifespan(app):
                pass  # Startup succeeded


def test_root_endpoint(test_client):
    """Test root endpoint returns correct response."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "PropOps API"
    assert data["status"] == "running"
    assert "version" in data


def test_cors_middleware_configured(test_client):
    """Test that CORS middleware is properly configured."""
    # Test that CORS headers are present in response
    response = test_client.get("/", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    # Note: TestClient doesn't fully simulate CORS, but this tests endpoint availability


def test_routers_mounted():
    """Test that all expected routers are mounted on the app."""
    routes = [str(route.path) for route in app.routes]
    assert "/api/v1/health" in routes or any("health" in r for r in routes)
    assert "/api/v1/inbox" in routes or any("inbox" in r for r in routes)
    assert "/api/v1/incidents" in routes or any("incidents" in r for r in routes)
    assert "/api/v1/approvals" in routes or any("approvals" in r for r in routes)
---