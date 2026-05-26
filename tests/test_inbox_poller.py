"""Tests for inbox poller service."""
import asyncio
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select

from backend.core.database import Base
from backend.models.incident import Incident, AIDraft, CommunicationLog, Organization
from backend.services.inbox_poller import (
    InboxPoller,
    process_email,
    _decode_header_value,
    _get_email_body,
    _check_duplicate,
    start_inbox_poller,
    stop_inbox_poller,
)


@pytest.fixture
async def test_db():
    """Create in-memory SQLite async database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Create test org
    async with async_session() as session:
        org = Organization(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            name="Test Org",
        )
        session.add(org)
        await session.commit()
    
    yield async_session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


class TestDecodeHeaderValue:
    """Tests for email header decoding."""

    def test_plain_ascii(self):
        """Should handle plain ASCII headers."""
        result = _decode_header_value("John Doe <john@example.com>")
        assert result == "John Doe <john@example.com>"

    def test_empty(self):
        """Should handle empty headers."""
        result = _decode_header_value("")
        assert result == ""

    def test_none(self):
        """Should handle None."""
        result = _decode_header_value(None)
        assert result == ""


class TestGetEmailBody:
    """Tests for email body extraction."""

    def test_plain_text_email(self):
        """Should extract plain text from simple email."""
        import email
        msg = email.message_from_string(
            "Subject: Test\nContent-Type: text/plain\n\nHello World"
        )
        body = _get_email_body(msg)
        assert "Hello World" in body

    def test_multipart_email(self):
        """Should extract plain text from multipart."""
        import email
        msg = email.message.EmailMessage()
        msg["Subject"] = "Test"
        msg["From"] = "test@example.com"
        msg.set_content("Plain text body")
        body = _get_email_body(msg)
        assert "Plain text body" in body

    def test_empty_email(self):
        """Should return empty string for no content."""
        import email
        msg = email.message_from_string("Subject: Test\n\n")
        body = _get_email_body(msg)
        assert body == ""


class TestCheckDuplicate:
    """Tests for deduplication logic."""

    @pytest.mark.asyncio
    async def test_no_duplicate(self, test_db):
        """Should return False for new Message-ID."""
        async with test_db() as session:
            result = await _check_duplicate(session, "msg-123")
            assert result is False

    @pytest.mark.asyncio
    async def test_with_duplicate(self, test_db):
        """Should return True for existing Message-ID."""
        async with test_db() as session:
            # Create existing communication log
            comm_log = CommunicationLog(
                id=uuid.uuid4(),
                incident_id=uuid.uuid4(),
                thread_id=uuid.uuid4(),
                direction="inbound",
                channel="email",
                sender="test@example.com",
                raw_headers={"message_id": "msg-123"},
            )
            session.add(comm_log)
            await session.commit()

        # Check duplicate
        async with test_db() as session:
            result = await _check_duplicate(session, "msg-123")
            assert result is True


class TestProcessEmail:
    """Tests for email processing pipeline."""

    @pytest.mark.asyncio
    async def test_process_email_success(self, test_db):
        """Should create incident, draft, and communication log."""
        async with test_db() as session:
            with patch("backend.services.inbox_poller.triage_message") as mock_triage, \
                 patch("backend.services.inbox_poller.generate_draft") as mock_draft:
                
                # Mock triage response
                mock_triage.return_value = MagicMock(
                    success=True,
                    category="maintenance",
                    urgency="HIGH",
                    title="Broken pipe",
                    summary="Tenant reports water leak",
                    confidence=0.95,