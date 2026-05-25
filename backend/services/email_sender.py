"""SMTP email sending service for approved drafts.

Sends approved AI drafts via SMTP and logs communication.
Handles errors gracefully — marks draft as send_failed on SMTP error.
Updates incident status to IN_PROGRESS on first outbound send.

SECURITY-REVIEW: This module handles SMTP credentials and email content.
- SMTP credentials are read from settings (never hardcoded or logged)
- Email bodies are HTML-escaped to prevent injection
- Send status is logged but not email content (privacy)
"""
import html
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.config import settings
from backend.models.incident import AIDraft, Incident, CommunicationLog

logger = logging.getLogger(__name__)


def _html_safe_body(plain_text: str) -> str:
    """Convert plain text body to HTML-safe format.
    
    Converts newlines to <br> tags, escapes HTML entities to prevent injection.
    
    Args:
        plain_text: Plain text email body
    
    Returns:
        HTML-safe body with escaped entities and br tags
    """
    escaped = html.escape(plain_text)
    html_body = escaped.replace("\n", "<br>\n")
    return html_body


def _send_smtp(
    to_email: str,
    subject: str,
    body: str,
) -> tuple[bool, Optional[str]]:
    """Send email via SMTP synchronously.
    
    Validates configuration, builds MIME message, connects to SMTP server,
    and sends. Handles authentication and connection errors.
    
    IMPORTANT: Email is sent synchronously. For background use, call this
    from a background task (see send_approved_draft).
    
    Args:
        to_email: Recipient email address
        subject: Email subject line
        body: Plain text email body (will be converted to HTML)
    
    Returns:
        (success: bool, error_message: Optional[str])
        - On success: (True, None)
        - On failure: (False, error_message_string)
    """
    try:
        # SECURITY-REVIEW: Validate SMTP config before attempting send
        if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
            error_msg = "SMTP configuration incomplete (check SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD)"
            logger.error(f"email_sender: {error_msg}")
            return False, error_msg
        
        # Validate recipient email format (basic check)
        if not to_email or "@" not in to_email:
            error_msg = f"Invalid recipient email format: {to_email}"
            logger.error(f"email_sender: {error_msg}")
            return False, error_msg
        
        # Create MIME message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_username
        msg["To"] = to_email
        
        # Attach plain text part
        msg.attach(MIMEText(body, "plain"))
        
        # Attach HTML part (with converted newlines and escaped content)
        html_body = _html_safe_body(body)
        html_part = f"""
        <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <p>{html_body}</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin-top: 20px;">
                <p style="color: #999; font-size: 12px;">
                    Sent by PropOps on behalf of your property management company.
                </p>
            </body>
        </html>
        """
        msg.attach(MIMEText(html_part, "html"))
        
        # Send via SMTP with timeout
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        
        # Log success (without email body for privacy)
        logger.info(
            f"email_sender: sent email to {to_email} subject='{subject[:50]}' "
            f"smtp_host={settings.smtp_host}"
        )
        return True, None
    
    except smtplib.SMTPAuthenticationError as e:
        error_msg = f"SMTP authentication failed (check SMTP_USERNAME and SMTP_PASSWORD)"
        logger.error(f"email_sender: {error_msg} — {str(e)}")
        return False, error_msg
    
    except smtplib.SMTPNotSupportedError as e:
        error_msg = f"SMTP server does not support required feature"
        logger.error(f"email_sender: {error_msg} — {str(e)}")
        return False, error_msg
    
    except smtplib.SMTPException as e:
        error_msg = f"SMTP server error: {str(e)}"
        logger.error(f"email_sender: {error_msg}")
        return False, error_msg
    
    except TimeoutError as e:
        error_msg = f"SMTP connection timeout (host {settings.smtp_host}:{settings.smtp_port})"
        logger.error(f"email_sender: {error_msg} — {str(e)}")
        return False, error_msg
    
    except Exception as e:
        error_msg = f"Unexpected error sending email: {str(e)}"
        logger.error(f"email_sender: {error_msg}", exc_info=True)
        return False, error_msg


async def send_approved_draft(
    db: AsyncSession,
    draft_id: str,
    approved_by: str,
) -> None:
    """Send an approved draft via SMTP and update DB status.
    
    Background task function that:
    1. Fetches the approved draft from DB
    2. Sends email via _send_smtp()
    3. Updates draft.status to "sent" or "send_failed"
    4. Creates CommunicationLog entry
    5. Updates incident.status to IN_PROGRESS if first outbound
    
    This function is designed to be called via BackgroundTasks.add_task()
    from the approve_draft endpoint. If DB/SMTP fails, logs error and marks
    draft as send_failed. Does not raise exceptions (safe for background).
    
    Args:
        db: AsyncSession for database operations
        draft_id: UUID string of the draft to send
        approved_by: User ID/email who approved the draft
    
    Returns:
        None (void function; all status updates to DB)
    """
    draft_uuid: Optional[uuid.UUID] = None
    draft: Optional[AIDraft] = None
    incident: Optional[Incident] = None
    
    try:
        # Parse and fetch draft
        try:
            draft_uuid = uuid.UUID(draft_id)
        except ValueError:
            logger.error(f"send_approved_draft: Invalid draft_id format: {draft_id}")
            return
        
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
        
        if not draft:
            logger.error(f"send_approved_draft: Draft not found: {draft_id}")
            return
        
        # Fetch incident for status update
        result = await db.execute(select(Incident).where(Incident.id == draft.incident_id))
        incident = result.scalar_one_or_none()
        
        if not incident:
            logger.error(
                f"send_approved_draft: Incident not found for draft {draft_id}: "
                f"incident_id={draft.incident_id}"
            )
            return
        
        logger.info(
            f"send_approved_draft: Sending draft {draft_id} to {draft.recipient_email} "
            f"for incident {draft.incident_id}"
        )
        
        # Send email via SMTP
        success, error_message = _send_smtp(
            to_email=draft.recipient_email,
            subject=draft.subject,
            body=draft.body
        )
        
        # Update draft status based on send result
        if success:
            draft.status = "sent"
            draft.sent_at = datetime.now(timezone.utc)
            logger.info(f"send_approved_draft: Draft {draft_id} sent successfully")
        else:
            draft.status = "send_failed"
            draft.send_error = error_message
            draft.send_failed_at = datetime.now(timezone.utc)
            logger.warning(
                f"send_approved_draft: Draft {draft_id} send failed: {error_message}"
            )
        
        # Create communication log entry
        try:
            comm_log = CommunicationLog(
                id=str(uuid.uuid4()),
                incident_id=draft.incident_id,
                direction="outbound",
                channel="email",
                recipient=draft.recipient_email,
                subject=draft.subject,
                body=draft.body[:1000],  # Truncate for logging
                status="sent" if success else "failed",
                error=error_message if error_message else None,
                sent_by=approved_by,
                created_at=datetime.now(timezone.utc),
            )
            db.add(comm_log)
            logger.debug(f"send_approved_draft: Created communication log for draft {draft_id}")
        except Exception as e:
            logger.error(
                f"send_approved_draft: Failed to create communication log for draft {draft_id}: {e}",
                exc_info=True
            )
        
        # Update incident status to IN_PROGRESS if first outbound send
        if success and incident.status == "OPEN":
            incident.status = "IN_PROGRESS"
            incident.updated_at = datetime.now(timezone.utc)
            logger.info(
                f"send_approved_draft: Updated incident {draft.incident_id} "
                f"status to IN_PROGRESS"
            )
        
        # Commit all changes
        await db.commit()
        logger.info(f"send_approved_draft: Completed for draft {draft_id}")
    
    except Exception as e:
        # Rollback on any error
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.error(f"send_approved_draft: Rollback error: {rollback_error}")
        
        logger.error(
            f"send_approved_draft: Unexpected error for draft {draft_id}: {e}",
            exc_info=True
        )
---