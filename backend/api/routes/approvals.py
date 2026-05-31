"""Approval queue API routes."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.incident import AIDraft, Incident
from backend.services.email_sender import send_approved_draft

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
APPROVER_ROLES = frozenset({"founder", "admin", "approver"})


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
    raw_message: str | None = None


class PendingDraftsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    drafts: list[DraftApprovalResponse]
    total: int
    limit: int
    offset: int


class ApproveRequest(BaseModel):
    approved_by: str = "founder"


class RejectRequest(BaseModel):
    reason: str = ""


class CountResponse(BaseModel):
    pending: int


def _org_filter(user: dict[str, Any]):
    """Return org_id UUID filter when user is org-scoped.

    Global roles (founder/admin/approver) intentionally skip org filter — single-tenant
    beta where approvers see all pending drafts. Tighten when multi-tenant RBAC lands.
    """
    role = user.get("role", "user")
    org_id = user.get("org_id")
    if role in APPROVER_ROLES or not org_id:
        return None
    try:
        return uuid.UUID(str(org_id))
    except ValueError:
        raise HTTPException(status_code=403, detail={"error": "invalid_org_scope"})


def _assert_can_mutate_draft(user: dict[str, Any], incident: Incident) -> None:
    """Ensure authenticated user may approve/reject drafts for this incident."""
    role = user.get("role", "user")
    if role not in APPROVER_ROLES:
        raise HTTPException(
            status_code=403,
            detail={"error": "insufficient_role", "message": "Approver role required"},
        )
    user_org = user.get("org_id")
    if (
        user_org
        and role not in ("founder", "admin")
        and str(incident.org_id) != str(user_org)
    ):
        raise HTTPException(
            status_code=403,
            detail={"error": "org_access_denied", "message": "Draft belongs to another org"},
        )


def _pending_base_query(org_uuid: uuid.UUID | None):
    stmt = (
        select(AIDraft, Incident)
        .join(Incident, AIDraft.incident_id == Incident.id)
        .where(AIDraft.status == "pending")
    )
    if org_uuid is not None:
        stmt = stmt.where(Incident.org_id == org_uuid)
    return stmt.order_by(Incident.created_at.desc())


@router.get("/count", response_model=CountResponse)
async def pending_count(
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> CountResponse:
    """Fast count of pending drafts for nav badge."""
    org_uuid = _org_filter(user)
    stmt = select(func.count()).select_from(AIDraft).where(AIDraft.status == "pending")
    if org_uuid is not None:
        stmt = stmt.join(Incident, AIDraft.incident_id == Incident.id).where(
            Incident.org_id == org_uuid
        )
    count = (await db.execute(stmt)).scalar_one() or 0
    return CountResponse(pending=count)


@router.get("/pending", response_model=PendingDraftsResponse)
async def list_pending_approvals(
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> PendingDraftsResponse:
    """List pending AI drafts with pagination and org scoping."""
    org_uuid = _org_filter(user)

    count_stmt = select(func.count()).select_from(AIDraft).where(AIDraft.status == "pending")
    if org_uuid is not None:
        count_stmt = count_stmt.join(Incident, AIDraft.incident_id == Incident.id).where(
            Incident.org_id == org_uuid
        )
    total = (await db.execute(count_stmt)).scalar_one() or 0

    result = await db.execute(
        _pending_base_query(org_uuid).limit(limit).offset(offset)
    )
    rows = result.all()
    drafts = [
        DraftApprovalResponse(
            draft_id=str(d.id),
            incident_id=str(d.incident_id),
            incident_title=inc.title,
            urgency=inc.urgency or "MEDIUM",
            subject=d.subject or "",
            body=d.body or "",
            recipient=d.recipient_email or "",
            created_at=d.created_at.isoformat() if d.created_at else "",
            raw_message=inc.raw_message,
        )
        for d, inc in rows
    ]
    return PendingDraftsResponse(drafts=drafts, total=total, limit=limit, offset=offset)


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
        draft_uuid = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "invalid draft_id"})

    result = await db.execute(
        select(AIDraft, Incident)
        .join(Incident, AIDraft.incident_id == Incident.id)
        .where(AIDraft.id == draft_uuid)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "Draft not found"})
    draft, incident = row

    _assert_can_mutate_draft(user, incident)

    if draft.status != "pending":
        raise HTTPException(status_code=400, detail={"error": f"Draft is already {draft.status}"})

    draft.status = "approved"
    draft.approved_by = req.approved_by or user.get("email") or user.get("id", "founder")
    draft.approved_at = datetime.now(timezone.utc)

    try:
        background_tasks.add_task(send_approved_draft, draft)
    except Exception as e:
        logger.warning("Could not queue email send: %s", e)

    logger.info("Draft %s approved by %s", draft_id, draft.approved_by)
    return {"status": "approved", "draft_id": draft_id}


@router.post("/{draft_id}/reject")
async def reject_draft(
    draft_id: str,
    req: RejectRequest,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """Reject a draft."""
    try:
        draft_uuid = uuid.UUID(draft_id)
    except ValueError:
        raise HTTPException(status_code=422, detail={"error": "invalid draft_id"})

    result = await db.execute(
        select(AIDraft, Incident)
        .join(Incident, AIDraft.incident_id == Incident.id)
        .where(AIDraft.id == draft_uuid)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail={"error": "Draft not found"})
    draft, incident = row

    _assert_can_mutate_draft(user, incident)

    draft.status = "rejected"
    draft.rejected_at = datetime.now(timezone.utc)
    draft.rejection_reason = req.reason
    logger.info("Draft %s rejected by %s", draft_id, user.get("email", user.get("id")))
    return {"status": "rejected", "draft_id": draft_id}
