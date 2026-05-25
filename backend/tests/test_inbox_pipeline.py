"""Tests for the inbox processing pipeline."""
import json
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from sqlalchemy import select

from backend.services.inbox_poller import process_email
from backend.models.incident import Incident, AIDraft, CommunicationLog


class TestInboxPipeline:
    """Test suite for email to incident to draft pipeline."""

    @pytest.mark.asyncio
    async def test_full_email_to_draft_flow(self, test_db, org, property_obj):
        """Test complete pipeline: email → triage → incident → draft."""
        org_id = str(org.id)
        
        with patch("backend.services.inbox_poller.triage_message") as mock_triage, \
             patch("backend.services.inbox_poller.generate_draft") as mock_draft:
            
            # Mock triage response
            mock_triage.return_value = MagicMock(
                category="maintenance",
                urgency="HIGH",
                title="Broken pipe",
                summary="Water leak",
                confidence=0.95,
            )
            
            # Mock draft response
            mock_draft.return_value = MagicMock(
                subject="Re: Broken pipe",
                body="We will send a plumber.",
                model_used="claude-sonnet-4-5-20251001",
                success=True,
            )
            
            async with test_db() as db:
                incident_id = await process_email(
                    db=db,
                    org_id=org_id,
                    sender="tenant@example.com",
                    subject="Pipe broken",
                    body="Water dripping from ceiling",
                    message_id="msg-123",
                )
            
            assert incident_id is not None
            
            # Verify incident was created
            async with test_db() as db:
                result = await db.execute(select(Incident).where(Incident.id == uuid.UUID(incident_id)))
                incident = result.scalar_one()
                
                assert incident.title == "Broken pipe"
                assert incident.urgency == "HIGH"
                assert incident.category == "maintenance"
                assert incident.status == "PENDING_APPROVAL"
                assert incident.source_address == "tenant@example.com"
            
            # Verify draft was created
            async with test_db() as db:
                result = await db.execute(select(AIDraft).where(AIDraft.incident_