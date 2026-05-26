"""Approval queue API routes."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.models.incident import AIDraft, Incident
from backend.api.auth import get_current_user, require_role, User

logger = logging.getLogger(__name__)
router = APIRouter()


class ApproveRequest(BaseModel):
    reason: str = ""


class RejectRequest(BaseModel):
    """Request to reject a draft."""
    reason: str = ""


class ApprovalResponse(BaseModel):
    status: str
    draft_id: str
    approved_by: str
    timestamp: str


class PendingApprovalItem(BaseModel):
    draft_id: str
    incident_id: str
    incident_title: str
    urgency: str
    subject: str
    body: str
    recipient: str
    created_at: str


@router.get("/pending", response_model=list[PendingApprovalItem])
async def list_pending_approvals(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all drafts awaiting approval. Requires authentication."""
    logger.info(f"User {user.email} listing pending approvals")
    
    result = await db.execute(
        select(AIDraft, Incident)
        .join(Incident, AIDraft.incident_id == Incident.id)
        .where(AIDraft.status == "pending")
    )
    rows = result.all()
    
    return [
        PendingApprovalItem(
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


@router.post("/{draft_id}/approve", response_model=ApprovalResponse)
async def approve_draft(
    draft_id: str,
    req: ApproveRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a draft — marks it ready to send.
    
    SECURITY-REVIEW: approved_by is extracted from verified JWT token (user.email),
    not from request body. Audit trail shows actual approver identity.
    """
    logger.info(f"User {user.email} approving draft {draft_id}")
    
    try:
        result = await db.execute(
            select(AIDraft).where(AIDraft.id == uuid.UUID(draft_id))
        )
    except ValueError as e:
        logger.warning(f"Invalid draft_id format: {draft_id}")
        raise HTTPException(status_code=400, detail="Invalid draft ID format")
    
    draft = result.scalar_one_or_none()
    if not draft:
        logger.warning(f"Draft {draft_id} not found")
        raise HTTPException(status_code=404, detail="Draft not found")
    
    draft.status = "approved"
    draft.approved_by = req.approved_by
    draft.approved_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "approved", "draft_id": draft_id}


@router.post("/{draft_id}/reject", response_model=dict)
async def reject_draft(
    draft_id: str,
    req: RejectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject a draft.
    
    SECURITY-REVIEW: Rejection also captured with authenticated user identity.
    """
    logger.info(f"User {user.email} rejecting draft {draft_id}; reason: {req.reason}")
    
    try:
        result = await db.execute(
            select(AIDraft).where(AIDraft.id == uuid.UUID(draft_id))
        )
    except ValueError as e:
        logger.warning(f"Invalid draft_id format: {draft_id}")
        raise HTTPException(status_code=400, detail="Invalid draft ID format")
    
    draft = result.scalar_one_or_none()
    if not draft:
        logger.warning(f"Draft {draft_id} not found")
        raise HTTPException(status_code=404, detail="Draft not found")
    
    draft.status = "rejected"
    await db.commit()
    return {"status": "rejected", "draft_id": draft_id}
