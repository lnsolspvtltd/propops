"""Tests for approval queue endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4
from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI, HTTPException

from backend.api.routes import approvals as approvals_module
from backend.api.routes.approvals import router
from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.incident import AIDraft


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock()


@pytest.fixture
def mock_draft():
    """Mock AIDraft instance."""
    draft = MagicMock(spec=AIDraft)
    draft.id = uuid4()
    draft.incident_id = uuid4()
    draft.subject = "Test Subject"
    draft.body = "Test Body"
    draft.status = "pending"
    draft.recipient_email = "test@example.com"
    draft.created_at = datetime.now(timezone.utc)
    draft.approved_by = None
    draft.approved_at = None
    return draft


@pytest.fixture
def app_with_router(mock_db):
    app = FastAPI()
    app.include_router(router)

    async def _override_user():
        return {"id": "founder", "email": "founder@example.com"}

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db] = _override_db
    yield app
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_approve_draft_success(mock_draft, app_with_router, mock_db):
    """Test successful draft approval with authenticated user."""
    draft_id = str(mock_draft.id)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_draft
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("backend.api.routes.approvals.send_approved_draft"):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_router), base_url="http://test"
        ) as client:
            response = await client.post(
                f"/api/v1/approvals/{draft_id}/approve",
                json={"approved_by": "founder"},
                headers={"Authorization": "Bearer valid-token"},
            )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert mock_draft.status == "approved"


@pytest.mark.asyncio
async def test_approve_draft_invalid_format(app_with_router):
    """Test approval with malformed draft_id returns 422."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_router), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/approvals/not-a-uuid/approve",
            json={},
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_approve_draft_not_found(app_with_router, mock_db):
    """Test approval when draft doesn't exist returns 404."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    async with AsyncClient(
        transport=ASGITransport(app=app_with_router), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/approvals/{uuid4()}/approve",
            json={},
            headers={"Authorization": "Bearer valid-token"},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_approve_draft_auth_required():
    """Test that approval requires authentication."""
    app = FastAPI()
    app.include_router(router)

    async def _raise_auth():
        raise HTTPException(status_code=401, detail="Not authenticated")

    app.dependency_overrides[get_current_user] = _raise_auth

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/approvals/{uuid4()}/approve",
            json={},
        )

    assert response.status_code == 401
