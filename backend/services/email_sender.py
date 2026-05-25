"""SMTP email sending service for approved drafts.

Sends approved AI drafts via SMTP and logs communication.
Handles errors gracefully — marks draft as send_failed on SMTP error.
Updates incident status to IN_PROGRESS on first outbound send.
"""
import logging
from datetime import datetime
from typing import Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from backend.core.config import settings
from backend.models.incident import AIDraft, Incident, CommunicationLog

logger = logging.getLogger(__name__)


def _html_safe_body(plain_text: str) -> str:
    """Convert plain text body to HTML-safe format.
    
    Converts newlines to <br> tags, escapes HTML entities.
    """
    import html
    escaped = html.escape(plain_text)
    html_body = escaped.replace("\n", "<br>\n")
    return html_body


def _send_smtp(
    to_email: str,
    subject: str,
    body: str,
) -> tuple[bool, Optional[str]]:
    """Send email via SMTP synchronously.
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Plain text email body
    
    Returns:
        (success: bool, error_message: Optional[str])
    """
    try:
        # Validate configuration
        if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
            return False, "SMTP configuration incomplete"
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_username
        msg["To"] = to_email
        
        # Plain text part
        msg.attach(MIMEText(body, "plain"))
        
        # HTML part (convert newlines to br)
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
        
        # Send via SMTP
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
        
        logger.info(f"email_sender: sent email to {to_email} subject='{subject[:50]}'")
        return True, None
    
    except smtplib.SMTPAuthenticationError as e:
        msg = f"SMTP auth failed: {str(e)}"
        logger.error(f"email_sender: {msg}")
        return False, msg
    
    except smtplib.SMTPException as e:
        msg = f"SMTP error: {str(e)}"
        logger.error(f"email_sender: {msg}")
        return False, msg
    
    except Exception as e:
        msg = f"Unexpected error sending email: {str(e)}"
        logger.error(f"email_sender: {msg}", exc_info=True)
        return False, msg


async def send_approved_draft(
    db: AsyncSession,
    draft_id: str,
    approved_by: str,
) -> dict:
    """Send an approved draft via SMTP.
    
    Updates:
    1. ai_drafts.status → 'sent' or 'send_failed'
    2. ai_drafts.sent_at → current time (on success)
    3. communication_logs → creates 'outbound' entry
    4. incident.status → 'IN_PROGRESS' (on first outbound send)
    
    Args:
        db: AsyncSession
        draft_id: UUID of the draft to send
        approved_by: Email/user identifier who approved
    
    Returns:
        {
            "success": bool,
            "draft_id": str,
            "status": "sent" | "send_failed",
            "error": Optional[str]
        }
    """
    # Fetch draft with incident
    draft_result = await db.execute(
        select(AIDraft).where(AIDraft.id == uuid.UUID(draft_id))
    )
    draft = draft_result.scalar_one_or_none()
    
    if not draft:
        logger.error(f"email_sender: draft {draft_id} not found")
        return {
            "success": False,
            "draft_id": draft_id,
            "status": "not_found",
            "error": "Draft not found"
        }
    
    if draft.status != "approved":
        logger.warning(f"email_sender: draft {draft_id} status is {draft.status}, not approved")
        return {
            "success": False,
            "draft_id": draft_id,
            "status": draft.status,
            "error": f"Draft status is {draft.status}, expected approved"
        }
    
    # Fetch incident
    incident_result = await db.execute(
        select(Incident).where(Incident.id == draft.incident_id)
    )
    incident = incident_result.scalar_one_or_none()
    
    if not incident:
        logger.error(f"email_sender: incident {draft.incident_id} not found for draft {draft_id}")
        return {
            "success": False,
            "draft_id": draft_id,
            "status": "incident_not_found",
            "error": "Incident not found"
        }
    
    # Send email via SMTP
    success, error_msg = _send_smtp(
        to_email=draft.recipient_email,
        subject=draft.subject,
        body=draft.body,
    )
    
    # Update draft status
    if success:
        draft.status = "sent"
        draft.sent_at = datetime.utcnow()
        logger.info(f"email_sender: draft {draft_id} marked as sent")
    else:
        draft.status = "send_failed"
        logger.warning(f"email_sender: draft {draft_id} marked as send_failed: {error_msg}")
    
    # Create communication log entry (outbound)
    comm_log = CommunicationLog(
        id=uuid.uuid4(),
        incident_id=incident.id,
        thread_id=incident.thread_id,
        direction="outbound",
        channel="email",
        sender=settings.smtp_username,
        recipient=draft.recipient_email,
        subject=draft.subject,
        body=draft.body,
        created_at=datetime.utcnow(),
    )
    db.add(comm_log)
    
    # Update incident status to IN_PROGRESS on first outbound send
    if success and incident.status in ["OPEN", "PENDING_APPROVAL"]:
        incident.status = "IN_PROGRESS"
        incident.updated_at = datetime.utcnow()
        logger.info(f"email_sender: incident {incident.id} status updated to IN_PROGRESS")
    
    await db.commit()
    
    return {
        "success": success,
        "draft_id": draft_id,
        "status": draft.status,
        "error": error_msg
    }
</end>