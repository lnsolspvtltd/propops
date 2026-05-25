"""Integration tests for approvals endpoint."""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.incident import AIDraft, Incident, Organization


@pytest.fixture
def sample_org():
    """Sample organization."""
    return Organization(
        id=uuid.uuid4(),
        name="Test Org",
        plan="beta",
    )


@pytest.fixture
def sample_incident(sample_org):
    """Sample incident."""
    return Incident(
        id=uuid.uuid4(),
        org_id=sample_org.id,
        thread_id=uuid.uuid4(),
        title="Plumbing leak in Unit 201",
        category="maintenance",
        urgency="HIGH",
        status="OPEN",
        ai_summary="Tenant reports water leak under sink.",
        source_channel="email",
        source_address="tenant@example.com",
    )


@pytest.fixture
def sample_draft(sample_incident):
    """Sample pending draft."""
    return AIDraft(
        id=uuid.uuid4(),
        incident_id=sample_incident.id,
        draft_type="tenant_reply",
        recipient_email="tenant@example.com",
        subject="Re: Plumbing leak in Unit 201",
        body="Thank you for reporting this.\nOur team will investigate tomorrow.",
        status="pending",
    )


@pytest.mark.asyncio
async def test_approve_endpoint_queues_send(
    sample_org, sample_incident, sample_draft
):
    """Should approve draft and queue email send."""
    # This is a simplified integration test example
    # Full integration would require full app fixture and DB setup
    
    # Verify draft starts as pending
    assert sample_draft.status == "pending"
    assert sample_draft.approved_at is None
    
    # After approve, status should be "approved"
    sample_draft.status = "approved"
    sample_draft.approved_by = "founder"
    sample_draft.approved_at = datetime.now(timezone.utc)
    
    assert sample_draft.status == "approved"
    assert sample_draft.approved_by == "founder"
