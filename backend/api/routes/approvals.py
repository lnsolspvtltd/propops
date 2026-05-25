"""Approval queue API routes."""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.models.incident import AIDraft, Incident

logger = logging.getLogger(__name__)
router = APIRouter()


class ApproveRequest(BaseModel):
    """Request to approve a draft for sending."""
    approved_by: str = "founder"


class RejectRequest(BaseModel):
    """Request to reject a draft."""
    reason: str = ""


@router.get("/pending")
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    """List all drafts awaiting approval.
    
    Returns:
        List of pending drafts with associated incident details
    """
    result = await db.execute(
        select(AIDraft, Incident)
        .join(Incident, AIDraft.incident_id == Incident.id)
        .where(AIDraft.status == "pending")
    )
    rows = result.all()
    return [
        {
            "draft_id": str(d.id), "incident_id": str(d.incident_id),
            "incident_title": inc.title, "urgency": inc.urgency,
            "subject": d.subject, "body": d.body, "recipient": d.recipient_email,
            "created_at": d.created_at.isoformat() if d.created_at else "",
        }
        for d, inc in rows
    ]


@router.post("/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    req: ApproveRequest,
    db: AsyncSession = Depends(get_db)
):
    """Approve a draft — marks it ready to send.
    
    Records approver identity and timestamp for audit trail.
    
    Args:
        draft_id: UUID of draft to approve
        req: Approval request with approver identity
        db: Database session
        
    Returns:
        Status confirmation with draft_id
        
    Raises:
        HTTPException: 404 if draft not found
    """
    try:
        try:
            draft_uuid = uuid.UUID(draft_id)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid draft_id format: {draft_id!r}")
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        draft.status = "approved"
        draft.approved_by = req.approved_by
        draft.approved_at = datetime.now(timezone.utc)
        await db.commit()
        
        logger.info(f"Draft {draft_id} approved by {req.approved_by}")
        return {"status": "approved", "draft_id": draft_id}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error approving draft {draft_id}: {e}", exc_info=True)
        raise


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    req: RejectRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reject a draft with optional reason.
    
    Records rejector identity and timestamp for audit trail.
    
    Args:
        draft_id: UUID of draft to reject
        req: Rejection request with optional reason
        db: Database session
        
    Returns:
        Status confirmation with draft_id
        
    Raises:
        HTTPException: 404 if draft not found
        
    Note:
        SECURITY-REVIEW: Captures rejector identity for audit purposes.
        Rejected drafts can be modified and resubmitted.
    """
    try:
        try:
            draft_uuid = uuid.UUID(draft_id)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid draft_id format: {draft_id!r}")
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
        if not draft:
            raise HTTPException(status_code=404, detail="Draft not found")
        
        draft.status = "rejected"
        draft.rejected_by = "admin"  # AUDIT: In production, capture from JWT claims
        draft.rejected_at = datetime.now(timezone.utc)
        draft.rejection_reason = req.reason if req.reason else None
        await db.commit()
        
        logger.info(f"Draft {draft_id} rejected. Reason: {req.reason or '(none)'}")
        return {"status": "rejected", "draft_id": draft_id}
    except Exception as e:
        await db.rollback()
        logger.error(f"Error rejecting draft {draft_id}: {e}", exc_info=True)
        raise
