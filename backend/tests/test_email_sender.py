"""Unit tests for email_sender service."""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.email_sender import send_approved_draft, _html_safe_body, _send_smtp
from backend.models.incident import AIDraft, Incident, CommunicationLog


@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_incident():
    """Sample incident."""
    return Incident(
        id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        thread_id=uuid.uuid4(),
        title="Test incident",
        category="maintenance",
        urgency="HIGH",
        status="OPEN",
        ai_summary="Summary",
        source_channel="email",
        source_address="tenant@example.com",
    )


@pytest.fixture
def sample_draft(sample_incident):
    """Sample approved draft."""
    return AIDraft(
        id=uuid.uuid4(),
        incident_id=sample_incident.id,
        draft_type="tenant_reply",
        recipient_email="recipient@example.com",
        subject="Re: Test incident",
        body="Thank you for reporting this issue.\nWe will investigate.",
        status="approved",
        approved_by="founder",
        approved_at=datetime.utcnow(),
    )


class TestHtmlSafeBody:
    """Tests for _html_safe_body function."""

    def test_converts_newlines_to_br(self):
        """Should convert newline characters to <br> tags."""
        text = "Line 1\nLine 2\nLine 3"
        result = _html_safe_body(text)
        assert "<br>" in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_escapes_html_entities(self):
        """Should escape HTML special characters."""
        text = "<script>alert('xss')</script>"
        result = _html_safe_body(text)
        assert "&lt;script&gt;" in result
        assert "<script>" not in result

    def test_preserves_text_content(self):
        """Should preserve actual text content."""
        text = "Hello & goodbye"
        result = _html_safe_body(text)
        assert "Hello &amp; goodbye" in result


class TestSendSmtp:
    """Tests for _send_smtp function."""

    @patch("backend.services.email_sender.smtplib.SMTP")
    def test_successful_send(self, mock_smtp_class):
        """Should successfully send email."""
        # Setup mock
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        # Call
        success, error = _send_smtp(
            to_email="test@example.com",
            subject="Test",
            body="Test body"
        )

        # Assert
        assert success is True
        assert error is None
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once()
        mock_server.send_message.assert_called_once()

    @patch("backend.services.email_sender.smtplib.SMTP")
    def test_smtp_auth_error(self, mock_smtp_class):
        """Should handle SMTP authentication error."""
        import smtplib
        mock_smtp_class.return_value.__enter__.return_value.login.side_effect = (
            smtplib.SMTPAuthenticationError(535, "Invalid credentials")
        )

        success, error = _send_smtp(
            to_email="test@example.com",
            subject="Test",
            body="Test body"
        )

        assert success is False
        assert "auth failed" in error.lower()

    def test_missing_smtp_config(self):
        """Should fail gracefully if SMTP not configured."""
        with patch("backend.services.email_sender.settings") as mock_settings:
            mock_settings.smtp_host = ""
            mock_settings.smtp_username = ""
            mock_settings.smtp_password = ""

            success, error = _send_smtp(
                to_email="test@example.com",
                subject="Test",
                body="Test body"
            )

            assert success is False
            assert "configuration" in error.lower()


class TestSendApprovedDraft:
    """Tests for send_approved_draft function."""

    @pytest.mark.asyncio
    async def test_draft_not_found(self, mock_db):
        """Should return error if draft not found."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = await send_approved_draft(mock_db, str(uuid.uuid4()), "founder")

        assert result["success"] is False
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_draft_not_approved(self, mock_db, sample_draft):
        """Should return error if draft status is not 'approved'."""
        sample_draft.status = "pending"
        mock_db.execute.return_value.scalar_one_or_none.return_value = sample_draft

        result = await send_approved_draft(mock_db, str(sample_draft.id), "founder")

        assert result["success"] is False
        assert "expected approved" in result["error"]

    @pytest.mark.asyncio
    async def test_incident_not_found(self, mock_db, sample_draft):
        """Should return error if incident not found."""
        # First call returns draft, second call returns None (incident)
        draft_result = MagicMock()
        draft_result.scalar_one_or_none.return_value = sample_draft
        
        incident_result = MagicMock()
        incident_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [draft_result, incident_result]

        result = await send_approved_draft(mock_db, str(sample_draft.id), "founder")

        assert result["success"] is False
        assert result["status"] == "incident_not_found"

    @pytest.mark.asyncio
    async def test_successful_send(self, mock_db, sample_draft, sample_incident):
        """Should successfully send draft and update statuses."""
        # Setup mocks
        draft_result = MagicMock()
        draft_result.scalar_one_or_none.return_value = sample_draft
        
        incident_result = MagicMock()
        incident_result.scalar_one_or_none.return_value = sample_incident

        mock_db.execute.side_effect = [draft_result, incident_result]
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("backend.services.email_sender._send_smtp") as mock_send:
            mock_send.return_value = (True, None)

            result = await send_approved_draft(mock_db, str(sample_draft.id), "founder")

        assert result["success"] is True
        assert result["status"] == "sent"
        assert sample_draft.status == "sent"
        assert sample_draft.sent_at is not None
        assert sample_incident.status == "IN_PROGRESS"
        mock_db.add.assert_called_once()  # communication_log added
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_failure(self, mock_db, sample_draft, sample_incident):
        """Should mark draft as send_failed on SMTP error."""
        draft_result = MagicMock()
        draft_result.scalar_one_or_none.return_value = sample_draft
        
        incident_result = MagicMock()
        incident_result.scalar_one_or_none.return_value = sample_incident

        mock_db.execute.side_effect = [draft_result, incident_result]
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        with patch("backend.services.email_sender._send_smtp") as mock_send:
            mock_send.return_value = (False, "SMTP connection failed")

            result = await send_approved_draft(mock_db, str(sample_draft.id), "founder")

        assert result["success"] is False
        assert result["status"] == "send_failed"
        assert sample_draft.status == "send_failed"
        assert sample_draft.sent_at is None  # Not set on failure
        assert sample_incident.status == "OPEN"  # Not updated on failure

    @pytest.mark.asyncio
    async def test_creates_communication_log(self, mock_db, sample_draft, sample_incident):
        """Should create communication_logs entry for outbound email."""
        draft_result = MagicMock()
        draft_result.scalar_one_or_none.return_value = sample_draft
        
        incident_result = MagicMock()
        incident_result.scalar_one_or_none.return_value = sample_incident

        mock_db.execute.side_effect = [draft_result, incident_result]
        added_items = []
        mock_db.add = lambda item: added_items.append(item)
        mock_db.commit = AsyncMock()

        with patch("backend.services.email_sender._send_smtp") as mock_send:
            mock_send.return_value = (True, None)

            await send_approved_draft(mock_db, str(sample_draft.id), "founder")

        # Find the CommunicationLog in added items
        comm_logs = [item for item in added_items if isinstance(item, CommunicationLog)]
        assert len(comm_logs) == 1
        log = comm_logs[0]
        assert log.direction == "outbound"
        assert log.channel == "email"
        assert log.recipient == sample_draft.recipient_email
        assert log.subject == sample_draft.subject
</end>