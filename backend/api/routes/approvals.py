"""Approval queue API routes."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.core.database import get_db
from backend.models.incident import AIDraft, Incident
from backend.services.email_sender import send_approved_draft

router = APIRouter()


class ApproveRequest(BaseModel):
    approved_by: str = "founder"


class RejectRequest(BaseModel):
    reason: str = ""


@router.get("/pending")
async def list_pending_approvals(db: AsyncSession = Depends(get_db)):
    """List all drafts awaiting approval."""
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """Approve a draft and send it via SMTP.
    
    1. Marks draft as 'approved' with approved_at timestamp
    2. Immediately sends email via SMTP (background task)
    3. Updates draft status to 'sent' or 'send_failed'
    4. Creates communication_logs entry
    5. Updates incident.status to IN_PROGRESS if first outbound
    """
    try:
        draft_uuid = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid draft_id format")
    result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    if draft.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Draft status is {draft.status}, expected pending"
        )
    
    # Mark as approved
    draft.status = "approved"
    draft.approved_by = req.approved_by
    draft.approved_at = datetime.now(timezone.utc)
    await db.commit()
    
    # Queue email send as background task
    background_tasks.add_task(send_approved_draft, db, draft_id, req.approved_by)
    
    return {
        "status": "approved",
        "draft_id": draft_id,
        "message": "Draft approved. Email will be sent shortly."
    }


@router.post("/{draft_id}/reject")
async def reject_draft(draft_id: str, req: RejectRequest, db: AsyncSession = Depends(get_db)):
    """Reject a draft."""
    try:
        draft_uuid = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid draft_id format")
    result = await db.execute(select(AIDraft).where(AIDraft.id == draft_uuid))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    
    if draft.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Draft status is {draft.status}, expected pending"
        )
    
    draft.status = "rejected"
    # Persist rejection metadata if model supports it
    if hasattr(draft, "rejection_reason"):
        draft.rejection_reason = req.reason
    if hasattr(draft, "rejected_at"):
        draft.rejected_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "rejected", "draft_id": draft_id, "reason": req.reason}
