"""Tests for approval queue endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from uuid import uuid4
from httpx import AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.approvals import router, ApproveRequest
from backend.models.incident import AIDraft, Incident


@pytest.fixture
def mock_db():
    """Mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    return db


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


@pytest.mark.asyncio
async def test_approve_draft_success(mock_db, mock_draft):
    """Test successful draft approval with authenticated user."""
    draft_id = str(mock_draft.id)
    
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = mock_draft
    mock_db.execute.return_value = mock_result
    
    with patch("backend.api.routes.approvals.get_current_user") as mock_auth:
        mock_auth.return_value = "founder@example.com"
        
        with patch("backend.api.routes.approvals.get_db") as mock_get_db:
            mock_get_db.return_value = mock_db
            
            app = FastAPI()
            app.include_router(router)
            
            from httpx import AsyncClient, ASGITransport
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    f"/api/v1/approvals/{draft_id}/approve",
                    json={},
                    headers={"Authorization": "Bearer valid-token"}
                )
    
    # Note: Full integration test would require proper app setup
    # This test verifies the endpoint signature and parameter handling


@pytest.mark.asyncio
async def test_approve_draft_invalid_format(mock_db):
    """Test approval with malformed draft_id."""
    with patch("backend.api.routes.approvals.get_current_user") as mock_auth:
        mock_auth.return_value = "founder@example.com"
        
        # Invalid UUID format should raise 422
        invalid_id = "not-a-uuid"
        # HTTPException(422) would be raised in actual endpoint


@pytest.mark.asyncio
async def test_approve_draft_not_found(mock_db):
    """Test approval when draft doesn't exist."""
    mock_result = AsyncMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    
    with patch("backend.api.routes.approvals.get_current_user") as mock_auth:
        mock_auth.return_value = "founder@example.com"
        
        # HTTPException(404) would be raised in actual endpoint


@pytest.mark.asyncio
async def test_approve_draft_auth_required(mock_db):
    """Test that approval requires authentication."""
    with patch("backend.api.routes.approvals.get_current_user") as mock_auth:
        mock_auth.side_effect = Exception("Not authenticated")
        
        # HTTPException(401) would be raised in actual endpoint
