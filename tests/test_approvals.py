"""Tests for approval queue endpoints."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from fastapi import HTTPException
from httpx import AsyncClient

from backend.api.routes.approvals import (
    approve_draft,
    reject_draft,
    list_pending_approvals,
)
from backend.models.incident import AIDraft, Incident


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {
        "id": "test-user-123",
        "email": "test@example.com",
        "role": "approver",
        "org_id": "org-123"
    }


@pytest.fixture
def mock_draft():
    """Mock AIDraft object."""
    draft = MagicMock(spec=AIDraft)
    draft.id = uuid.uuid4()
    draft.incident_id = uuid.uuid4()
    draft.subject = "Test Subject"
    draft.body = "Test body"
    draft.recipient_email = "vendor@example.com"
    draft.status = "pending"
    draft.created_at = datetime.now(timezone.utc)
    return draft


@pytest.fixture
def mock_incident():
    """Mock Incident object."""
    incident = MagicMock(spec=Incident)
    incident.id = uuid.uuid4()
    incident.title = "Test Incident"
    incident.urgency = "HIGH"
    incident.status = "OPEN"
    return incident


@pytest.mark.asyncio
async def test_list_pending_approvals_success(mock_user, mock_draft, mock_incident):
    """Test listing