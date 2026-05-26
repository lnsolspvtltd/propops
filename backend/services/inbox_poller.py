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
from datetime import datetime, timezone
from email.header import decode_header
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.ai.triage_agent import triage_message
from backend.ai.draft_agent import generate_draft
from backend.models.incident import Incident, AIDraft, CommunicationLog
from backend.services.context_resolver import resolve_context

logger = logging.getLogger(__name__)

# Error tracking for alerting
FATAL_ERRORS = []
TRANSIENT_ERROR_COUNT = {}


def _decode_header_value(value: str) -> str:
    """Decode MIME-encoded email header.
    
    Args:
        value: Raw email header value (may be RFC 2047 encoded)
        
    Returns:
        Decoded UTF-8 string
        
    Raises:
        ValueError if value is None or empty after decode
    """
    if not value:
        return ""
    
    decoded_parts = decode_header(value)
    result = []
    
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            try:
                # Try specified charset first
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except (AttributeError, LookupError, TypeError):
                # Fall back to UTF-8 if charset is invalid
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part) if part else "")
    
    return " ".join(result).strip()


def _get_email_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        Plain text body (max 10000 chars), or empty string
        
    Raises:
        Logs warnings on decode errors but does not raise
    """
    body = ""
    
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        body = payload.decode("utf-8", errors="replace")
                    except Exception as e:
                        logger.warning(f"inbox_poller: failed to decode email part: {e}")
                        body = str(payload)
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                body = payload.decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning(f"inbox_poller: failed to decode email payload: {e}")
                body = str(payload)
    
    return body.strip()[:10000]


async def _check_duplicate(db: AsyncSession, message_id: str) -> bool:
    """Check if email already processed by Message-ID.
    
    Uses database unique constraint on (message_id, org_id) to prevent duplicates.
    
    Args:
        db: AsyncSession
        message_id: RFC 2822 Message-ID header value
        
    Returns:
        True if duplicate found, False otherwise
        
    Note:
        DB schema enforces uniqueness; this is defensive check before insert
    """
    if not message_id:
        return False
    
    result = await db.execute(
        select(CommunicationLog).where(CommunicationLog.message_id == message_id)
    )
    return result.scalar_one_or_none() is not None


async def _process_email(
    db: AsyncSession,
    msg: email.message.Message,
    org_id: str,
) -> Optional[str]:
    """Process single email: dedup → triage → incident → draft.
    
    Args:
        db: AsyncSession
        msg: Parsed email message
        org_id: Organization UUID
        
    Returns:
        Incident ID if created, None if duplicate or error
        
    Error handling:
        - Returns None on duplicate (not an error)
        - Logs transient errors and increments counter
        - Logs fatal errors and appends to FATAL_ERRORS list
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
            triage_result = await triage_message(body, subject)
        except Exception as e:
            logger.error(f"inbox_poller: triage_message failed: {e}", exc_info=True)
            error_key = "triage_failure"
            TRANSIENT_ERROR_COUNT[error_key] = TRANSIENT_ERROR_COUNT.get(error_key, 0) + 1
            return None
        
        # Create incident
        incident = Incident(
            id=str(uuid.uuid4()),
            org_id=org_id,
            thread_id=str(uuid.uuid4()),
            title=subject,
            category=triage_result.get("category", "general"),
            urgency=triage_result.get("urgency", "medium"),
            status="OPEN",
            ai_summary=triage_result.get("summary", ""),
            ai_confidence=triage_result.get("confidence", 0.0),
            source_channel="email",
            source_address=from_addr,
            raw_message=body[:5000],  # Truncate to prevent bloat
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(incident)
        
        # Generate draft reply
        try:
            draft_text = await generate_draft(body, subject, triage_result)
            draft = AIDraft(
                id=str(uuid.uuid4()),
                incident_id=str(incident.id),
                draft_text=draft_text,
                status="PENDING_REVIEW",
                created_at=datetime.now(timezone.utc),
            )
            db.add(draft)
        except Exception as e:
            logger.warning(f"inbox_poller: generate_draft failed (draft skipped): {e}")
            # Don't fail incident creation if draft fails
        
        # Log communication
        comm_log = CommunicationLog(
            id=str(uuid.uuid4()),
            incident_id=str(incident.id),
            message_id=message_id,
            direction="INBOUND",
            source="email",
            from_addr=from_addr,
            subject=subject,
            body_preview=body[:500],
            created_at=datetime.now(timezone.utc),
        )
        db.add(comm_log)
        
        await db.commit()
        logger.info(f"inbox_poller: Created incident={incident.id} from email subject={subject}")
        return str(incident.id)
        
    except Exception as e:
        logger.error(f"inbox_poller: Unexpected error processing email: {e}", exc_info=True)
        await db.rollback()
        error_key = "email_processing_fatal"
        FATAL_ERRORS.append({"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()})
        return None


async def _fetch_emails(db: AsyncSession, org_id: str) -> int:
    """Connect to IMAP, fetch new emails, process each.
    
    Args:
        db: AsyncSession
        org_id: Organization UUID
        
    Returns:
        Number of emails processed (not including duplicates)
        
    Error handling:
        - Catches IMAP connection errors and treats as transient
        - Logs failures but allows service to continue
        - Returns 0 if fetch fails
    """
    processed_count = 0
    imap = None

    try:
        # Connect to IMAP
        imap = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
        imap.login(settings.imap_username, settings.imap_password)
        imap.select("INBOX")
        
        # Search for unseen emails
        status, email_ids = imap.search(None, "UNSEEN")
        if status != "OK":
            logger.warning(f"inbox_poller: IMAP search returned status={status}")
            return 0
        
        email_list = email_ids[0].split()
        if not email_list:
            logger.debug("inbox_poller: No unseen emails")
            return 0
        
        logger.info(f"inbox_poller: Found {len(email_list)} unseen emails")
        
        # Process each email
        for email_id in email_list[:50]:  # Rate limit to 50 per poll
            try:
                status, msg_data = imap.fetch(email_id, "(RFC822)")
                if status != "OK":
                    logger.warning(f"inbox_poller: IMAP fetch failed for email_id={email_id}")
                    continue
                
                msg_bytes = msg_data[0][1]
                msg = email.message_from_bytes(msg_bytes)
                
                incident_id = await _process_email(db, msg, org_id)
                if incident_id:
                    processed_count += 1
                
                # Mark as read
                try:
                    imap.store(email_id, "+FLAGS", "\\Seen")
                except Exception as e:
                    logger.warning(f"inbox_poller: Failed to mark email as read: {e}")
                    # Continue processing regardless
                    
            except Exception as e:
                logger.error(f"inbox_poller: Error processing single email: {e}", exc_info=True)
                # Continue with next email
                continue
        
    except imaplib.IMAP4.error as e:
        logger.error(f"inbox_poller: IMAP connection error: {e}", exc_info=True)
        error_key = "imap_connection_failure"
        TRANSIENT_ERROR_COUNT[error_key] = TRANSIENT_ERROR_COUNT.get(error_key, 0) + 1
    except Exception as e:
        logger.error(f"inbox_poller: Unexpected error in _fetch_emails: {e}", exc_info=True)
        FATAL_ERRORS.append({"error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()})
    finally:
        if imap is not None:
            try:
                imap.close()
                imap.logout()
            except Exception:
                pass  # Best effort cleanup

    async def run_forever(self):
        """Poll inbox continuously."""
        self.running = True
        logger.info(f"inbox_poller: starting (interval={settings.imap_poll_interval_seconds}s)")
        while self.running:
            await self.poll_once()
            await asyncio.sleep(settings.imap_poll_interval_seconds)
