"""Inbox polling service — IMAP ingestion.

Polls the configured IMAP inbox every N seconds.
For each new email:
  1. Checks deduplication (Message-ID in DB)
  2. Runs AI triage
  3. Creates incident
  4. Generates draft reply
  5. Marks email as READ

Error handling: Logs and continues on transient errors; alerts on fatal failures.
Uses structured error tracking to distinguish retryable vs non-recoverable errors.
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
    try:
        # Extract headers
        message_id = msg.get("Message-ID", "")
        from_addr = msg.get("From", "unknown")
        subject = _decode_header_value(msg.get("Subject", "(no subject)"))
        
        # SECURITY-REVIEW: Sanitize headers to prevent injection attacks
        subject = subject.replace("\x00", "").replace("\n", " ").replace("\r", "")[:500]
        from_addr = from_addr.replace("\x00", "").replace("\n", " ").replace("\r", "")[:255]
        
        # Check deduplication
        if await _check_duplicate(db, message_id):
            logger.info(f"inbox_poller: Skipping duplicate message-id={message_id[:50]}")
            return None
        
        # Extract body
        body = _get_email_body(msg)
        if not body:
            logger.warning(f"inbox_poller: Email has empty body: subject={subject}, from={from_addr}")
            return None
        
        # Run triage
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

    return processed_count


# Global task handle
_inbox_poller_task: Optional[asyncio.Task] = None


async def _poller_loop():
    """Infinite loop: poll IMAP every N seconds.
    
    Graceful error handling:
      - Catches and logs errors per poll cycle
      - Continues polling on transient errors
      - Tracks fatal errors for alerting
    """
    logger.info(f"inbox_poller: Starting poller loop (interval={settings.imap_poll_interval_seconds}s)")
    
    while True:
        try:
            async with AsyncSessionLocal() as db:
                # FIXME: org_id should be configurable per-org polling
                # For now, hardcoded to first/default org
                org_id = settings.default_org_id
                processed = await _fetch_emails(db, org_id)
                if processed > 0:
                    logger.info(f"inbox_poller: Processed {processed} emails")
                    
        except Exception as e:
            logger.error(f"inbox_poller: Error in poll cycle: {e}", exc_info=True)
            # Continue polling despite errors
        
        await asyncio.sleep(settings.imap_poll_interval_seconds)


async def start_inbox_poller():
    """Start background inbox poller task.
    
    Error handling:
        If poller fails to start, logs error but does NOT block app startup.
        Application degrades gracefully (manual inbox ingestion still available).
    """
    global _inbox_poller_task
    try:
        _inbox_poller_task = asyncio.create_task(_poller_loop())
        logger.info("inbox_poller: Background task started successfully")
    except Exception as e:
        logger.error(
            f"inbox_poller: Failed to start background poller: {e}. "
            f"Application will continue but automated email ingestion is disabled. "
            f"Manual incident creation and inbox API still available.",
            exc_info=True,
        )


async def stop_inbox_poller():
    """Stop background inbox poller task gracefully.
    
    Cancels task and waits for cleanup.
    """
    global _inbox_poller_task
    if _inbox_poller_task:
        try:
            _inbox_poller_task.cancel()
            await _inbox_poller_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"inbox_poller: Error stopping poller: {e}")
        logger.info("inbox_poller: Background task stopped")


def get_poller_health() -> dict:
    """Return health metrics for inbox poller.
    
    Returns:
        Dict with status, error counts, and recent fatal errors
    """
    return {
        "running": _inbox_poller_task is not None and not _inbox_poller_task.done(),
        "transient_errors": TRANSIENT_ERROR_COUNT,
        "fatal_errors_count": len(FATAL_ERRORS),
        "recent_fatal_errors": FATAL_ERRORS[-5:],  # Last 5
    }
---