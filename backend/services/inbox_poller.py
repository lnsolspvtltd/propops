"""Inbox polling service — IMAP ingestion.

Polls the configured IMAP inbox every N seconds.
For each new email:
  1. Checks deduplication (Message-ID in DB)
  2. Runs AI triage
  3. Creates incident
  4. Generates draft reply
  5. Marks email as READ

Never crashes — logs and continues on error.
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
from sqlalchemy import select

from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.ai.triage_agent import triage_message
from backend.ai.draft_agent import generate_draft
from backend.models.incident import Incident, AIDraft, CommunicationLog

logger = logging.getLogger(__name__)


def _decode_header_value(value: str) -> str:
    """Decode MIME-encoded email header.
    
    Args:
        value: Raw email header value (may be RFC 2047 encoded)
        
    Returns:
        Decoded UTF-8 string
    """
    decoded_parts = decode_header(value or "")
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            try:
                result.append(part.decode(charset or "utf-8", errors="replace"))
            except (AttributeError, LookupError):
                result.append(part.decode("utf-8", errors="replace"))
        else:
            result.append(str(part))
    return " ".join(result).strip()


def _get_email_body(msg: email.message.Message) -> str:
    """Extract plain text body from email message.
    
    Args:
        msg: email.message.Message object
        
    Returns:
        Plain text body (max 10000 chars), or empty string
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
                logger.warning(f"inbox_poller: failed to decode email: {e}")
                body = str(payload)
    
    return body.strip()[:10000]


async def _check_duplicate(db: AsyncSession, message_id: str) -> bool:
    """Check if email already processed by Message-ID.
    
    Args:
        db: AsyncSession
        message_id: RFC 2822 Message-ID header value
        
    Returns:
        True if duplicate found, False otherwise
    """
    result = await db.execute(
        select(CommunicationLog).where(CommunicationLog.raw_headers.contains({"message_id": message_id}))
    )
    return result.scalar_one_or_none() is not None


async def process_email(
    db: AsyncSession,
    org_id: str,
    sender: str,
    subject: str,
    body: str,
    message_id: str,
) -> Optional[str]:
    """Process a single inbound email. Returns incident_id or None.

    Steps:
    1. Check deduplication by Message-ID
    2. Triage with Claude Haiku
    3. Create incident
    4. Log communication
    5. Generate draft with Claude Sonnet
    6. Queue for approval

    Args:
        db: AsyncSession
        org_id: Organization UUID as string
        sender: Email address of sender
        subject: Email subject
        body: Plain text body
        message_id: RFC 2822 Message-ID

    Returns:
        Incident ID as string, or None if duplicate/error
    """
    try:
        # DEDUPLICATION: Check if we've seen this Message-ID
        if message_id and await _check_duplicate(db, message_id):
            logger.info(f"inbox_poller: skipping duplicate message {message_id}")
            return None

        # TRIAGE: Classify with AI
        triage = triage_message(body, sender=sender, subject=subject)
        if not triage.success:
            logger.warning(f"inbox_poller: triage failed for {sender}: {triage.error}")
            # Still create incident even if triage had issues — use defaults
            triage.category = triage.category or "general"
            triage.urgency = triage.urgency or "MEDIUM"
            triage.title = triage.title or f"Email from {sender}"
            triage.summary = triage.summary or body[:200]

        # CREATE INCIDENT
        incident = Incident(
            id=uuid.uuid4(),
            org_id=uuid.UUID(org_id) if isinstance(org_id, str) else org_id,
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

        # LOG COMMUNICATION
        comm_log = CommunicationLog(
            id=uuid.uuid4(),
            incident_id=incident.id,
            thread_id=incident.thread_id,
            direction="inbound",
            channel="email",
            sender=sender,
            subject=subject,
            body=body[:10000],
            raw_headers={"message_id": message_id},
        )
        db.add(comm_log)

        # DRAFT REPLY
        draft_result = generate_draft(
            incident_title=triage.title,
            incident_summary=triage.summary,
            category=triage.category,
            urgency=triage.urgency,
        )

        draft = AIDraft(
            id=uuid.uuid4(),
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
            f"inbox_poller: processed email from {sender} → incident {incident.id} [{triage.urgency}]"
        )
        return str(incident.id)

    except Exception as e:
        logger.error(f"inbox_poller: error processing email from {sender}: {e}", exc_info=True)
        await db.rollback()
        return None


class InboxPoller:
    """Polls IMAP inbox and processes new emails.
    
    - Connects via IMAP4_SSL
    - Fetches UNSEEN emails only
    - Marks as READ after processing
    - Resilient to connection errors (never crashes)
    """

    def __init__(self, org_id: str):
        """Initialize poller for organization.
        
        Args:
            org_id: Organization UUID
        """
        self.org_id = org_id
        self.running = False
        self._consecutive_errors = 0
        self._max_consecutive_errors = 5

    def _fetch_new_emails(self) -> list[tuple[str, str, str, str, bytes]]:
        """Fetch unread emails from IMAP.
        
        Returns:
            List of (sender, subject, body, message_id, msg_id_bytes)
            
        Handles errors gracefully — returns empty list on failure.
        """
        results = []
        mail = None
        try:
            # CONNECT
            mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
            mail.login(settings.imap_username, settings.imap_password)
            mail.select("INBOX")

            # SEARCH for UNSEEN
            _, msg_ids = mail.search(None, "UNSEEN")
            unread_ids = (msg_ids[0] or b"").split()

            if not unread_ids:
                logger.debug("inbox_poller: no unseen emails")
                return results

            logger.info(f"inbox_poller: found {len(unread_ids)} unseen emails")

            # FETCH each email
            for msg_id_bytes in unread_ids:
                try:
                    _, data = mail.fetch(msg_id_bytes, "(RFC822)")
                    if not data or not data[0]:
                        logger.warning(f"inbox_poller: empty data for msg {msg_id_bytes}")
                        continue

                    raw = data[0][1]
                    msg = email.message_from_bytes(raw)

                    sender = _decode_header_value(msg.get("From", ""))
                    subject = _decode_header_value(msg.get("Subject", "(no subject)"))
                    body = _get_email_body(msg)
                    mid = msg.get("Message-ID", f"<local-{msg_id_bytes.decode()}>")

                    if not body:
                        logger.warning(f"inbox_poller: empty body from {sender}, skipping")
                        continue

                    if not sender:
                        logger.warning(f"inbox_poller: no sender, skipping")
                        continue

                    results.append((sender, subject, body, mid, msg_id_bytes))

                except Exception as e:
                    logger.error(f"inbox_poller: error fetching msg {msg_id_bytes}: {e}")
                    continue

        except imaplib.IMAP4.abort as e:
            logger.error(f"inbox_poller: IMAP connection error: {e}")
            self._consecutive_errors += 1
        except imaplib.IMAP4.error as e:
            logger.error(f"inbox_poller: IMAP command error: {e}")
            self._consecutive_errors += 1
        except Exception as e:
            logger.error(f"inbox_poller: unexpected error: {e}", exc_info=True)
            self._consecutive_errors += 1
        finally:
            if mail:
                try:
                    mail.logout()
                except Exception as e:
                    logger.debug(f"inbox_poller: error during logout: {e}")

        return results

    def _mark_as_read(self, mail: imaplib.IMAP4_SSL, msg_id_bytes: bytes) -> bool:
        """Mark email as READ in IMAP.
        
        Args:
            mail: IMAP connection
            msg_id_bytes: Message ID bytes
            
        Returns:
            True on success, False on error
        """
        try:
            mail.store(msg_id_bytes, "+FLAGS", "\\Seen")
            return True
        except Exception as e:
            logger.error(f"inbox_poller: error marking msg {msg_id_bytes} as read: {e}")
            return False

    async def poll_once(self) -> int:
        """Single poll cycle — fetch and process emails.
        
        Returns:
            Number of emails processed
        """
        processed_count = 0

        # FETCH from IMAP
        emails = self._fetch_new_emails()

        if not emails:
            self._consecutive_errors = 0  # reset on successful empty poll
            return 0

        # PROCESS each email
        async with AsyncSessionLocal() as db:
            for sender, subject, body, message_id, msg_id_bytes in emails:
                try:
                    incident_id = await process_email(
                        db=db,
                        org_id=self.org_id,
                        sender=sender,
                        subject=subject,
                        body=body,
                        message_id=message_id,
                    )

                    if incident_id:
                        processed_count += 1

                    # MARK as READ in IMAP (best effort)
                    try:
                        mail = imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port)
                        mail.login(settings.imap_username, settings.imap_password)
                        mail.select("INBOX")
                        self._mark_as_read(mail, msg_id_bytes)
                        mail.logout()
                    except Exception as e:
                        logger.warning(f"inbox_poller: could not mark email as read: {e}")

                except Exception as e:
                    logger.error(
                        f"inbox_poller: failed to process email from {sender}: {e}",
                        exc_info=True,
                    )
                    continue

        if processed_count > 0:
            self._consecutive_errors = 0
            logger.info(f"inbox_poller: processed {processed_count} emails")

        return processed_count

    async def run_forever(self):
        """Poll inbox continuously.
        
        Runs every IMAP_POLL_INTERVAL_SECONDS seconds.
        Never crashes — logs and continues on error.
        """
        self.running = True
        logger.info(
            f"inbox_poller: starting (org_id={self.org_id}, interval={settings.imap_poll_interval_seconds}s)"
        )

        while self.running:
            try:
                await self.poll_once()

                # Back off if too many consecutive errors
                if self._consecutive_errors >= self._max_consecutive_errors:
                    backoff = min(300, 10 * self._consecutive_errors)
                    logger.warning(
                        f"inbox_poller: {self._consecutive_errors} consecutive errors, backing off for {backoff}s"
                    )
                    await asyncio.sleep(backoff)
                    self._consecutive_errors = 0
                else:
                    await asyncio.sleep(settings.imap_poll_interval_seconds)

            except asyncio.CancelledError:
                logger.info("inbox_poller: shutdown requested")
                self.running = False
                break
            except Exception as e:
                logger.error(f"inbox_poller: unhandled error in run loop: {e}", exc_info=True)
                await asyncio.sleep(settings.imap_poll_interval_seconds)

    def stop(self):
        """Stop the poller gracefully."""
        self.running = False
        logger.info("inbox_poller: stop requested")


# Global poller task
_poller_task: Optional[asyncio.Task] = None
_poller: Optional[InboxPoller] = None


async def start_inbox_poller(org_id: str = "00000000-0000-0000-0000-000000000001"):
    """Start background inbox poller task.
    
    Called from FastAPI lifespan startup.
    
    Args:
        org_id: Organization UUID to poll for (default: demo org)
    """
    global _poller_task, _poller
    try:
        # Only start if IMAP credentials are configured
        if not settings.imap_username or not settings.imap_password:
            logger.warning("inbox_poller: IMAP credentials not configured, skipping startup")
            return

        _poller = InboxPoller(org_id)
        _poller_task = asyncio.create_task(_poller.run_forever())
        logger.info("inbox_poller: background task started")
    except Exception as e:
        logger.error(f"inbox_poller: failed to start: {e}", exc_info=True)


async def stop_inbox_poller():
    """Stop background inbox poller task.
    
    Called from FastAPI lifespan shutdown.
    """
    global _poller_task, _poller
    if _poller:
        _poller.stop()
    if _poller_task:
        try:
            _poller_task.cancel()
            await asyncio.wait_for(_poller_task, timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("inbox_poller: timeout waiting for shutdown")
        except asyncio.CancelledError:
            logger.info("inbox_poller: task cancelled successfully")
        except Exception as e:
            logger.error(f"inbox_poller: error during shutdown: {e}")
```

---