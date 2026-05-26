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
from backend.core.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class ApproveRequest(BaseModel):
    """Request to approve a draft for sending."""
    pass


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
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Approve a draft — marks it ready to send.
    
    Records approver identity and timestamp for audit trail.
    
    Args:
        draft_id: UUID of draft to approve
        req: Approval request body (currently unused but reserved for future fields)
        current_user: Authenticated user from JWT or session
        db: Database session
        
    Returns:
        Status confirmation with draft_id
        
    Raises:
        HTTPException: 401 if not authenticated
        HTTPException: 404 if draft not found
        HTTPException: 422 if draft_id format invalid
    """
    try:
        try:
            draft_uuid = uuid.UUID(draft_id)
        except ValueError:
            logger.warning(f"Invalid draft_id format attempted: {draft_id!r}")
            raise HTTPException(status_code=422, detail=f"Invalid draft_id format: {draft_id!r}")
        
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
        if not draft:
            logger.warning(f"Draft not found: {draft_id}")
            raise HTTPException(status_code=404, detail="Draft not found")
        
        draft.status = "approved"
        draft.approved_by = current_user
        draft.approved_at = datetime.now(timezone.utc)
        await db.commit()
        
        logger.info(
            f"Draft {draft_id} approved by {current_user} at {draft.approved_at.isoformat()}",
            extra={"draft_id": draft_id, "approver": current_user, "action": "approve"}
        )
        return {"status": "approved", "draft_id": draft_id, "approved_by": current_user}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Error approving draft {draft_id}: {e}",
            exc_info=True,
            extra={"draft_id": draft_id, "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail="Failed to approve draft — see logs")


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    req: RejectRequest,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Reject a draft — marks it as rejected with reason for audit trail.
    
    Records rejector identity, reason, and timestamp.
    
    Args:
        draft_id: UUID of draft to reject
        req: Rejection request with reason
        current_user: Authenticated user from JWT or session
        db: Database session
        
    Returns:
        Status confirmation with draft_id and reason
        
    Raises:
        HTTPException: 401 if not authenticated
        HTTPException: 404 if draft not found
        HTTPException: 422 if draft_id format invalid
    """
    try:
        try:
            draft_uuid = uuid.UUID(draft_id)
        except ValueError:
            logger.warning(f"Invalid draft_id format attempted: {draft_id!r}")
            raise HTTPException(status_code=422, detail=f"Invalid draft_id format: {draft_id!r}")
        
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
        if not draft:
            logger.warning(f"Draft not found for rejection: {draft_id}")
            raise HTTPException(status_code=404, detail="Draft not found")
        
        draft.status = "rejected"
        draft.rejected_by = current_user
        draft.rejection_reason = req.reason
        draft.rejected_at = datetime.now(timezone.utc)
        await db.commit()
        
        logger.info(
            f"Draft {draft_id} rejected by {current_user} at {draft.rejected_at.isoformat()}. Reason: {req.reason[:100]}",
            extra={"draft_id": draft_id, "rejector": current_user, "action": "reject", "reason": req.reason}
        )
        return {
            "status": "rejected",
            "draft_id": draft_id,
            "rejected_by": current_user,
            "reason": req.reason
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(
            f"Error rejecting draft {draft_id}: {e}",
            exc_info=True,
            extra={"draft_id": draft_id, "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail="Failed to reject draft — see logs")
---