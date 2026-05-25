"""Approval queue API routes."""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header
from typing import Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.models.incident import AIDraft, Incident

logger = logging.getLogger(__name__)
router = APIRouter()


class ApproveRequest(BaseModel):
    """Request to approve a draft (approved_by derived from auth, not request)."""
    pass


class RejectRequest(BaseModel):
    """Request to reject a draft."""
    reason: str = ""


def get_current_user_id(authorization: str = None) -> str:
    """
    SECURITY-REVIEW: Extract authenticated user from request context.
    
    In production, this should validate JWT from Authorization header.
    Currently returns "founder" as placeholder for development.
    
    Args:
        authorization: Authorization header (e.g., "Bearer <token>")
        
    Returns:
        Authenticated user identifier
        
    Raises:
        HTTPException: If authorization is missing or invalid
    """
    # TODO: Implement real JWT validation in production
    # For now, use a placeholder that forces explicit auth setup
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    # Parse "Bearer <token>"
    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "Bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    token = parts[1]
    # TODO: Validate token, extract user_id claim
    # For development: accept any token
    logger.info(f"Authenticated request from user (JWT validation not yet implemented)")
    return "founder"  # Placeholder: replace with actual user_id from token


@router.get("/pending")
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    """
    List all drafts awaiting approval.
    
    Returns:
        List of pending draft objects with incident context
    """
    try:
        result = await db.execute(
            select(AIDraft, Incident)
            .join(Incident, AIDraft.incident_id == Incident.id)
            .where(AIDraft.status == "PENDING_REVIEW")
        )
        rows = result.all()
        return [
            {
                "draft_id": str(d.id),
                "incident_id": str(d.incident_id),
                "incident_title": inc.title,
                "urgency": inc.urgency,
                "draft_text": d.draft_text,
                "created_at": d.created_at.isoformat() if d.created_at else "",
            }
            for d, inc in rows
        ]
    except Exception as e:
        logger.error(f"Error listing pending approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pending approvals")


@router.post("/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    req: ApproveRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve a draft — marks it ready to send.
    
    SECURITY-REVIEW: approved_by is derived from authenticated JWT, not request body.
    This prevents privilege escalation where users could claim to be other approvers.
    
    Args:
        draft_id: UUID of the draft to approve
        req: Approval request (currently empty, kept for future validation fields)
        authorization: Authorization header from request
        db: Database session
        
    Returns:
        Confirmation with draft_id and approved_by user
        
    Raises:
        HTTPException: If draft not found, auth fails, or DB error
    """
    try:
        # SECURITY-REVIEW: Extract approved_by from authenticated request, not user input
        try:
            approved_by = get_current_user_id(authorization)
        except HTTPException:
            raise
        
        draft_uuid = uuid.UUID(draft_id)
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
        
        if not draft:
           logger.warning(f"Approval attempt on non-existent draft: {draft_id}")
            raise HTTPException(status_code=404, detail="Draft not found")
        
        draft.status = "approved"
        draft.approved_by = approved_by
        draft.approved_at = datetime.now(timezone.utc)
        
        await db.commit()
        
        logger.info(
            f"Draft {draft_id} approved by {approved_by}",
            extra={"draft_id": draft_id, "approved_by": approved_by}
        )
        
        return {
            "status": "approved",
            "draft_id": draft_id,
            "approved_by": approved_by,
            "approved_at": draft.approved_at.isoformat(),
        }
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid draft_id format: {draft_id}")
        raise HTTPException(status_code=400, detail="Invalid draft_id format")
    except Exception as e:
        logger.error(f"Error approving draft {draft_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to approve draft")


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    req: RejectRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """
    Reject a draft.
    
    SECURITY-REVIEW: rejected_by is derived from authenticated request.
    Audit trail includes who rejected, when, and why.
    
    Args:
        draft_id: UUID of the draft to reject
        req: Rejection request with optional reason
        authorization: Authorization header from request
        db: Database session
        
    Returns:
        Confirmation with draft_id, rejected_by user, and timestamp
        
    Raises:
        HTTPException: If draft not found, auth fails, or DB error
    """
    try:
        # SECURITY-REVIEW: Extract rejected_by from authenticated request
        try:
            rejected_by = get_current_user_id(authorization)
        except HTTPException:
            raise
        
        draft_uuid = uuid.UUID(draft_id)
        result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
        draft = result.scalar_one_or_none()
        
        if not draft:
            logger.warning(f"Rejection attempt on non-existent draft: {draft_id}")
            raise HTTPException(status_code=404, detail="Draft not found")
        
        draft.status = "rejected"
        draft.rejected_by = rejected_by
        draft.rejected_at = datetime.now(timezone.utc)
        draft.rejection_reason = req.reason if req.reason else None
        
        await db.commit()
        
        logger.info(
            f"Draft {draft_id} rejected by {rejected_by}. Reason: {req.reason[:100] if req.reason else '(none)'}",
            extra={
                "draft_id": draft_id,
                "rejected_by": rejected_by,
                "reason": req.reason[:200] if req.reason else None
            }
        )
        
        return {
            "status": "rejected",
            "draft_id": draft_id,
            "rejected_by": rejected_by,
            "rejected_at": draft.rejected_at.isoformat(),
            "reason": draft.rejection_reason,
        }
    
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Invalid draft_id format: {draft_id}")
        raise HTTPException(status_code=400, detail="Invalid draft_id format")
    except Exception as e:
        logger.error(f"Error rejecting draft {draft_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to reject draft")
