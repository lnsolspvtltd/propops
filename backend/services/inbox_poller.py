"""Inbox polling service — IMAP ingestion.

Polls the configured IMAP inbox every N seconds.
For each new email:
  1. Runs AI triage
  2. Creates or links to an incident
  3. Generates a draft reply
  4. Puts draft in approval queue
"""
import asyncio
import email
import imaplib
import logging
import uuid
from datetime import datetime
from email.header import decode_header
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.ai.triage_agent import triage_message
from backend.ai.draft_agent import generate_draft
from backend.models.incident import Incident, AIDraft, CommunicationLog

logger = logging.getLogger(__name__)


def _decode_header_value(value: str) -> str:
    """Decode MIME-encoded email header."""
    decoded_parts = decode_header(value or "")
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result)


def _get_email_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode("utf-8", errors="replace")
    return body.strip()


async def process_email(
    db: AsyncSession,
    org_id: str,
    sender: str,
    subject: str,
    body: str,
    message_id: str,
) -> Optional[str]:
    """
    Process a single inbound email. Returns incident_id or None.

    1. Triage with AI
    2. Create incident
    3. Log communication
    4. Generate draft
    5. Queue for approval
    """
    # AI triage
    triage = triage_message(body, sender=sender, subject=subject)

    # Create incident
    incident = Incident(
        id=uuid.uuid4(),
        org_id=org_id,
        thread_id=uuid.uuid4(),
        title=triage.title,
        category=triage.category,
        urgency=triage.urgency,
        status="PENDING_APPROVAL",
        ai_summary=triage.summary,
        ai_confidence=triage.confidence,
        source_channel="email",
        source_address=sender,
        raw_message=body[:10000],
    )
    db.add(incident)
    await db.flush()

    # Log inbound communication
    comm_log = CommunicationLog(
        incident_id=incident.id,
        thread_id=incident.thread_id,
        direction="inbound",
        channel="email",
        sender=sender,
        subject=subject,
        body=body[:10000],
    )
    db.add(comm_log)

    # Generate draft reply
    draft_result = generate_draft(
        incident_title=triage.title,
        incident_summary=triage.summary,
        category=triage.category,
        urgency=triage.urgency,
    )

    draft = AIDraft(
        incident_id=incident.id,
        draft_type="tenant_reply",
        recipient_email=sender,
        subject=draft_result.subject,
        body=draft_result.body,
        ai_model=draft_result.model_used,
        confidence=triage.confidence,
        status="pending",
    )
    db.add(draft)
    await db.commit()

    logger.info(f"inbox_poller: processed email from {sender} → incident {incident.id} [{triage.urgency}]")
    return str(incident.id)


class InboxPoller:
    """Polls IMAP inbox and processes new emails."""

    def __init__(self, org_id: str):
        self.org_id = org_id
        self.running = False

    def _fetch_new_emails(self) -> list[tuple[str, str, str, str]]:
        """Fetch unread emails. Returns list of (sender, subject, body, message_id)."""
        results = []
        try:
            mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
            mail.login(settings.imap_username, settings.imap_password)
            mail.select("INBOX")
            _, msg_ids = mail.search(None, "UNSEEN")
            for msg_id in (msg_ids[0] or b"").split():
                _, data = mail.fetch(msg_id, "(RFC822)")
                if data and data[0]:
                    raw = data[0][1]
                    msg = email.message_from_bytes(raw)
                    sender = _decode_header_value(msg.get("From", ""))
                    subject = _decode_header_value(msg.get("Subject", ""))
                    body = _get_email_body(msg)
                    mid = msg.get("Message-ID", str(msg_id))
                    if body:
                        results.append((sender, subject, body, mid))
            mail.logout()
        except Exception as e:
            logger.error(f"inbox_poller: IMAP error: {e}")
        return results

    async def poll_once(self):
        """Single poll cycle."""
        emails = self._fetch_new_emails()
        if not emails:
            return
        async with AsyncSessionLocal() as db:
            for sender, subject, body, message_id in emails:
                try:
                    await process_email(db, self.org_id, sender, subject, body, message_id)
                except Exception as e:
                    logger.error(f"inbox_poller: failed to process email: {e}")

    async def run_forever(self):
        """Poll inbox continuously."""
        self.running = True
        logger.info(f"inbox_poller: starting (interval={settings.imap_poll_interval_seconds}s)")
        while self.running:
            await self.poll_once()
            await asyncio.sleep(settings.imap_poll_interval_seconds)
