"""Tests for full inbox pipeline — email to incident to draft flow."""
import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.services.inbox_poller import process_email
from backend.models.incident import Incident, AIDraft, CommunicationLog
from backend.ai.triage_agent import TriageResult
from backend.ai.draft_agent import DraftResult


class TestInboxPipeline:
    """Test suite for full email → incident → draft pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_email_to_draft(self, db_session: AsyncSession, test_org):
        """Test complete flow: email ingestion → triage → incident → draft."""
        sender = "tenant@example.com"
        subject = "Water leak in bathroom"
        body = "There's water leaking from the pipe under the sink. Can you send someone?"

        # Mock triage agent
        mock_triage = TriageResult(
            category="maintenance",
            urgency="HIGH",
            title="Water leak in bathroom",
            summary="Tenant reports water leak from under sink",
            sentiment="concerned",
            unit_mentioned=None,
            requires_vendor=True,
            confidence=0.92,
            tags=["plumbing", "leak"],
            model_used="claude-haiku-4-5",
            success=True,
        )

        # Mock draft agent
        mock_draft = DraftResult(
            subject="Re: Water leak in bathroom",
            body="Thank you for reporting this. We will send a plumber to assess the situation.",
            draft_type="tenant_reply",
            model_used="claude-sonnet-4-5-20251001",
            success=True,
        )

        with patch("backend.services.inbox_poller.triage_message", return_value=mock_triage):
            with patch("backend.services.inbox_poller.generate_draft", return_value=mock_draft):
                incident_id = await process_email(
                    db=db_session,
                    org_id=str(test_org.id),
                    sender=sender,
                    subject=subject,
                    body=body,
                    message_id="msg-12345",
                )

        # Verify incident was created
        assert incident_id is not None
        result = await db_session.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
        incident = result.scalar_one_or_none()

        assert incident is not None
        assert incident.title == "Water leak in bathroom"
        assert incident.category == "maintenance"
        assert incident.urgency == "HIGH"
        assert incident.status == "PENDING_APPROVAL"
        assert incident.source_address == sender
        assert incident.ai_confidence == 0.92

        # Verify draft was created
        drafts_result = await db_session.execute(
            select(AIDraft).where(AIDraft.incident_id == incident.id)
        )
        draft = drafts_result.scalar_one_or_none()

        assert draft is not None
        assert draft.subject == "Re: Water leak in bathroom"
        assert draft.body == "Thank you for reporting this. We will send a plumber to assess the situation."
        assert draft.status == "pending"
        assert draft.recipient_email == sender

        # Verify communication log was created
        comm_result = await db_session.execute(
            select(CommunicationLog).where(CommunicationLog.incident_id == incident.id)
        )
        comm_log = comm_result.scalar_one_or_none()

        assert comm_log is not None
        assert comm_log.direction == "inbound"
        assert comm_log.channel == "email"
        assert comm_log.sender == sender

    @pytest.mark.asyncio
    async def test_pipeline_duplicate_email_ignored(self, db_session: AsyncSession, test_org):
        """Test that duplicate emails (same message_id) are handled gracefully."""
        sender = "tenant@example.com"
        subject = "Maintenance request"
        body = "Please fix the door lock"
        message_id = "msg-same-id-12345"

        mock_triage = TriageResult(
            category="maintenance",
            urgency="MEDIUM",
            title="Door lock repair",
            summary="Broken door lock",
            sentiment="neutral",
            confidence=0.85,
            tags=["lock", "security"],
            model_used="claude-haiku-4-5",
            success=True,
        )

        mock_draft = DraftResult(
            subject="Re: Door