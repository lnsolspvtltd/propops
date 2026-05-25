"""Inbox polling service — IMAP ingestion.

Polls the configured IMAP inbox every N seconds.
For each new email:
  1. Looks up sender in units (context resolution)
  2. Runs AI triage
  3. Creates or links to an incident
  4. Generates a draft reply
  5. Puts draft in approval queue
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
from backend.services.context_resolver import resolve_context

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

    Pipeline:
    1. Resolve sender to unit/property context (if tenant exists)
    2. AI triage to classify and extract urgency
    3. Create incident with resolved context
    4. Log communication
    5. Generate draft reply
    6. Queue for approval

    Args:
        db: Async database session
        org_id: Organization UUID
        sender: Sender email address
        subject: Email subject line
        body: Email body text
        message_id: Unique message identifier

    Returns:
        Incident ID (str) or None on failure
    """
    try:
        # Step 1: Resolve context (map sender to unit/property)
        context = await resolve_context(db, org_id, sender)
        
        logger.debug(
            f"inbox_poller: resolved context for {sender}: "
            f"unit={context.unit_id} property={context.property_id} confidence={context.confidence}"
        )

        # Step 2: AI triage
        triage = triage_message(body, sender=sender, subject=subject)

        # Step 3: Create incident with context
        incident = Incident(
            id=uuid.uuid4(),
            org_id=org_id,
            property_id=uuid.UUID(context.property_id) if context.property_id else None,
            unit_id=uuid.UUID(context.unit_id) if context.unit_id else None,
            thread_id=uuid.uuid4(),
            title=triage.title,
            category=triage.category,
            urgency=triage.urgency,
            status="PENDING_APPROVAL",
            ai_summary=triage.summary,
            # ai_confidence combines triage confidence with context resolution confidence
            # Use context confidence if we matched a unit, else triage confidence
            ai_confidence=context.confidence if context.unit_id else triage.confidence,
            source_channel="email",
            source_address=sender,
            raw_message=body[:10000],
        )
        db.add(incident)
        await db.flush()

        # Step 4: Log inbound communication
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

        # Step 5: Generate draft reply
        draft_result = generate_draft(
            incident_title=triage.title,
            incident_summary=triage.summary,
            category=triage.category,
            urgency=triage.urgency,
            tenant_name=context.tenant_name or "",
            property_name="",  # Could fetch from property_id if needed
            draft_type="tenant_reply",
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

        logger.info(
            f"inbox_poller: processed email from {sender} → incident {incident.id} "
            f"[{triage.urgency}] unit={context.unit_id} confidence={context.confidence:.2f}"
        )
        return str(incident.id)

    except Exception as e:
        logger.error(f"inbox_poller: failed to process email from {sender}: {e}", exc_info=True)
        return None


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
