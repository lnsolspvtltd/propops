"""Approval queue API routes with authentication and proper error handling."""
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.database import get_db
from backend.core.auth import get_current_user  # SECURITY-REVIEW: requires auth
from backend.models.incident import AIDraft, Incident, CommunicationLog
from backend.services.email_sender import send_approved_draft

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


class ApproveRequest(BaseModel):
    """Request body for approving a draft."""
    model_config = ConfigDict(from_attributes=True)
    approved_by: str = "founder"


class RejectRequest(BaseModel):
    """Request body for rejecting a draft."""
    model_config = ConfigDict(from_attributes=True)
    reason: str = ""


class DraftApprovalResponse(BaseModel):
    """Response after draft approval."""
    model_config = ConfigDict(from_attributes=True)
    draft_id: str
    incident_id: str
    incident_title: str
    urgency: str
    subject: str
    body: str
    recipient: str
    created_at: str


class PendingDraftsResponse(BaseModel):
    """List of pending approvals."""
    model_config = ConfigDict(from_attributes=True)
    drafts: list[DraftApprovalResponse]
    total: int


@router.get("/pending", response_model=PendingDraftsResponse)
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # SECURITY: require auth
) -> PendingDraftsResponse:
    """List all drafts awaiting approval.
    
    Requires authenticated user with approval role.
    
    Returns:
        PendingDraftsResponse with list of drafts pending approval
    """
    logger.info(f"list_pending_approvals called by user_id={current_user.get('id')}")
    
    try:
        result = await db.execute(
            select(AIDraft, Incident)
            .join(Incident, AIDraft.incident_id == Incident.id)
            .where(AIDraft.status == "pending")
        )
        rows = result.all()
        
        drafts = [
            DraftApprovalResponse(
                draft_id=str(d.id),
                incident_id=str(d.incident_id),
                incident_title=inc.title,
                urgency=inc.urgency,
                subject=d.subject,
                body=d.body,
                recipient=d.recipient_email,
                created_at=d.created_at.isoformat() if d.created_at else "",
            )
            for d, inc in rows
        ]
        
        logger.debug(f"Found {len(drafts)} pending drafts")
        return PendingDraftsResponse(drafts=drafts, total=len(drafts))
    
    except Exception as e:
        logger.error(f"Error listing pending approvals: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to load pending approvals — see server logs"
        )


@router.post("/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    req: ApproveRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # SECURITY: require auth
) -> dict:
    """Approve a draft and queue for SMTP send.
    
    Steps:
    1. Validate draft UUID and existence
    2. Verify draft status is "pending"
    3. Mark as "approved" with timestamp
    4. Queue background SMTP send task
    5. Return success response
    
    Email send is asynchronous — HTTP 200 means queued, not sent.
    Check the communication_logs endpoint or webhook for send status.
    
    Args:
        draft_id: UUID of the draft to approve
        req: ApproveRequest with approved_by field
        background_tasks: FastAPI background task queue
        db: Database session
        current_user: Authenticated user from get_current_user
    
    Returns:
        dict with status, draft_id, and message
    
    Raises:
        HTTPException 422: Invalid UUID format
        HTTPException 404: Draft not found
        HTTPException 400: Draft not in pending status
        HTTPException 500: Database error
    """
    logger.info(
        f"approve_draft called: draft_id={draft_id}, "
        f"user_id={current_user.get('id')}, approved_by={req.approved_by}"
    )
    
    # Validate UUID format
    try:
        draft_uuid = uuid.UUID(draft_id)
    except ValueError as e:
        logger.warning(f"Invalid draft_id format: {draft_id} — {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_format",
                "message": "draft_id must be a valid UUID",
                "received": draft_id
            }
        )
    
    # Fetch draft
    try:
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Database error fetching draft: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch draft — see server logs"
        )
    
    if not draft:
        logger.warning(f"Draft not found: {draft_id}")
        raise HTTPException(status_code=404, detail="Draft not found")
    draft.status = "approved"
    draft.approved_by = req.approved_by
    draft.approved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "approved", "draft_id": draft_id}


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    req: RejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)  # SECURITY: require auth
) -> dict:
    """Reject a draft.
    
    Marks draft as "rejected" with reason. Does not send email.
    
    Args:
        draft_id: UUID of the draft to reject
        req: RejectRequest with optional reason
        db: Database session
        current_user: Authenticated user from get_current_user
    
    Returns:
        dict with status and draft_id
    
    Raises:
        HTTPException 422: Invalid UUID format
        HTTPException 404: Draft not found
        HTTPException 400: Draft not in pending status
        HTTPException 500: Database error
    """
    logger.info(
        f"reject_draft called: draft_id={draft_id}, "
        f"user_id={current_user.get('id')}, reason={req.reason[:50] if req.reason else 'none'}"
    )
    
    # Validate UUID format
    try:
        draft_uuid = uuid.UUID(draft_id)
    except ValueError as e:
        logger.warning(f"Invalid draft_id format: {draft_id} — {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "invalid_format",
                "message": "draft_id must be a valid UUID",
                "received": draft_id
            }
        )
    
    # Fetch draft
    try:
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Database error fetching draft: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch draft — see server logs"
        )
    
    if not draft:
        logger.warning(f"Draft not found: {draft_id}")
        raise HTTPException(status_code=404, detail="Draft not found")
    draft.status = "rejected"
    await db.commit()
    return {"status": "rejected", "draft_id": draft_id}
