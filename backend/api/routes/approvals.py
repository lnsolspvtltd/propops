"""Approval queue API routes."""
import logging
import uuid
from datetime import datetime, timezone

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.incident import AIDraft, Incident
from backend.services.email_sender import send_approved_draft

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


class DraftApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    draft_id: str
    incident_id: str
    incident_title: str
    urgency: str
    subject: str
    body: str
    recipient: str
    created_at: str
    raw_message: str | None = None   # original tenant email for side-by-side display


class PendingDraftsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    drafts: list[DraftApprovalResponse]
    total: int


class ApproveRequest(BaseModel):
    approved_by: str = "founder"


class RejectRequest(BaseModel):
    reason: str = ""


class CountResponse(BaseModel):
    pending: int


@router.get("/count", response_model=CountResponse)
async def pending_count(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> CountResponse:
    """Fast count of pending drafts for nav badge."""
    count = (await db.execute(
        select(func.count()).select_from(AIDraft).where(AIDraft.status == "pending")
    )).scalar_one() or 0
    return CountResponse(pending=count)


@router.get("/pending", response_model=list[DraftApprovalResponse])
async def list_pending_approvals(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> list[DraftApprovalResponse]:
    """List all pending AI drafts with the original tenant email included."""
    result = await db.execute(
        select(AIDraft, Incident)
        .join(Incident, AIDraft.incident_id == Incident.id)
        .where(AIDraft.status == "pending")
        .order_by(Incident.created_at.desc())
    )
    rows = result.all()
    return [
        DraftApprovalResponse(
            draft_id=str(d.id),
            incident_id=str(d.incident_id),
            incident_title=inc.title,
            urgency=inc.urgency or "MEDIUM",
            subject=d.subject or "",
            body=d.body or "",
            recipient=d.recipient_email or "",
            created_at=d.created_at.isoformat() if d.created_at else "",
            raw_message=inc.raw_message or None,
        )
        for d, inc in rows
    ]


@router.post("/{draft_id}/approve")
async def approve_draft(
    draft_id: str,
    req: ApproveRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """Approve a draft and queue SMTP send."""
    try:
        uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "invalid draft_id"})

    result = await db.execute(select(AIDraft).where(AIDraft.id == uuid.UUID(draft_id)))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail={"error": "Draft not found"})
    if draft.status != "pending":
        raise HTTPException(status_code=400, detail={"error": f"Draft is already {draft.status}"})

    draft.status = "approved"
    draft.approved_by = req.approved_by or user.get("email") or user.get("id", "founder")
    draft.approved_at = datetime.now(timezone.utc)

    try:
        background_tasks.add_task(send_approved_draft, draft)
    except Exception as e:
        logger.warning("Could not queue email send: %s", e)

    logger.info("Draft %s approved by %s", draft_id, req.approved_by)
    return {"status": "approved", "draft_id": draft_id}


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    req: RejectRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """Reject a draft."""
    try:
        uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "invalid draft_id"})

    result = await db.execute(select(AIDraft).where(AIDraft.id == uuid.UUID(draft_id)))
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=404, detail={"error": "Draft not found"})

    draft.status = "rejected"
    draft.rejected_at = datetime.now(timezone.utc)
    draft.rejection_reason = req.reason
    logger.info("Draft %s rejected", draft_id)
    return {"status": "rejected", "draft_id": draft_id}