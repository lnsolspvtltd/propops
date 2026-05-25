"""Incidents API routes."""
import uuid
import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, ConfigDict
from backend.core.database import get_db
from backend.models.incident import Incident, AIDraft
from backend.services.incident_state_service import (
    transition_incident_status,
    get_incident_history,
    StateTransitionError,
)
from backend.core.state_machine import get_valid_transitions

logger = logging.getLogger(__name__)

router = APIRouter()


class IncidentResponse(BaseModel):
    """Incident response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    category: str
    urgency: str
    status: str
    ai_summary: Optional[str] = None
    source_address: Optional[str] = None
    created_at: str
    updated_at: str
    resolved_at: Optional[str] = None
    draft_count: int = 0


class StatusChangeRequest(BaseModel):
    """Request body for PATCH /incidents/{id}/status."""
    new_status: str
    actor: str = "human:unknown"
    reason: Optional[str] = None
    allow_override: bool = False


class StatusChangeResponse(BaseModel):
    """Response after status change."""
    incident_id: str
    from_status: str
    to_status: str
    changed: bool
    timestamp: str
    valid_next_states: list[str]


class HistoryEntry(BaseModel):
    """Single audit log entry."""
    id: str
    action: str
    actor: str
    details: dict
    created_at: str


class HistoryResponse(BaseModel):
    """Full incident history."""
    incident_id: str
    history: list[HistoryEntry]


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    status: Optional[str] = Query(None),
    urgency: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List incidents with optional filtering."""
    query = select(Incident).order_by(desc(Incident.created_at)).limit(limit)
    if status:
        query = query.where(Incident.status == status.upper())
    if urgency:
        query = query.where(Incident.urgency == urgency.upper())
    result = await db.execute(query)
    incidents = result.scalars().all()

    out = []
    for inc in incidents:
        draft_count_q = await db.execute(
            select(AIDraft).where(AIDraft.incident_id == inc.id, AIDraft.status == "pending")
        )
        out.append(IncidentResponse(
            id=str(inc.id),
            title=inc.title,
            category=inc.category or "",
            urgency=inc.urgency or "MEDIUM",
            status=inc.status or "OPEN",
            ai_summary=inc.ai_summary,
            source_address=inc.source_address,
            created_at=inc.created_at.isoformat() if inc.created_at else "",
            updated_at=inc.updated_at.isoformat() if inc.updated_at else "",
            resolved_at=inc.resolved_at.isoformat() if inc.resolved_at else None,
            draft_count=len(draft_count_q.scalars().all()),
        ))
    return out


@router.get("/{incident_id}")
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single incident with all drafts."""
    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    result = await db.execute(select(Incident).where(Incident.id == incident_uuid))
    inc = result.scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    drafts_q = await db.execute(select(AIDraft).where(AIDraft.incident_id == inc.id))
    drafts = [
        {
            "id": str(d.id),
            "subject": d.subject,
            "body": d.body,
            "status": d.status,
            "recipient": d.recipient_email,
        }
        for d in drafts_q.scalars().all()
    ]

    valid_next = get_valid_transitions(inc.status)

    return {
        "id": str(inc.id),
        "title": inc.title,
        "category": inc.category,
        "urgency": inc.urgency,
        "status": inc.status,
        "summary": inc.ai_summary,
        "source": inc.source_address,
        "raw_message": inc.raw_message,
        "created_at": inc.created_at.isoformat() if inc.created_at else "",
        "updated_at": inc.updated_at.isoformat() if inc.updated_at else "",
        "resolved_at": inc.resolved_at.isoformat() if inc.resolved_at else None,
        "valid_next_states": valid_next,
        "drafts": drafts,
    }


@router.patch("/{incident_id}/status", response_model=StatusChangeResponse)
async def change_incident_status(
    incident_id: str,
    req: StatusChangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Transition incident to a new status.

    Validates state machine rules before commit.
    Logs transition to audit trail.
    Returns 400 if transition is invalid.
    """
    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    try:
        result = await transition_incident_status(
            db=db,
            incident_id=incident_id,
            new_status=req.new_status,
            actor=req.actor,
            reason=req.reason,
            allow_override=req.allow_override,
        )
    except StateTransitionError as e:
        logger.warning(f"State transition error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error during status transition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    # Get valid next states
    valid_next = get_valid_transitions(result["to_status"])

    return StatusChangeResponse(
        incident_id=result["incident_id"],
        from_status=result["from_status"],
        to_status=result["to_status"],
        changed=result["changed"],
        timestamp=result["timestamp"],
        valid_next_states=valid_next,
    )


@router.post("/{incident_id}/reopen", response_model=StatusChangeResponse)
async def reopen_incident(
    incident_id: str,
    req: StatusChangeRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Explicitly re-open a RESOLVED incident.

    Requires explicit actor confirmation and reason.
    Only valid if incident is in RESOLVED state.
    """
    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    # Verify incident exists and is RESOLVED
    result = await db.execute(select(Incident).where(Incident.id == incident_uuid))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    if incident.status != "RESOLVED":
        raise HTTPException(
            status_code=400,
            detail=f"Incident is {incident.status}, not RESOLVED. Cannot reopen.",
        )

    if not req.reason:
        raise HTTPException(
            status_code=400,
            detail="Reason is required to reopen a resolved incident",
        )

    try:
        transition_result = await transition_incident_status(
            db=db,
            incident_id=incident_id,
            new_status="IN_PROGRESS",  # Default target for reopening
            actor=req.actor,
            reason=f"Reopened: {req.reason}",
            allow_override=True,
        )
    except StateTransitionError as e:
        logger.warning(f"Reopen failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    valid_next = get_valid_transitions(transition_result["to_status"])

    return StatusChangeResponse(
        incident_id=transition_result["incident_id"],
        from_status=transition_result["from_status"],
        to_status=transition_result["to_status"],
        changed=transition_result["changed"],
        timestamp=transition_result["timestamp"],
        valid_next_states=valid_next,
    )


@router.get("/{incident_id}/history", response_model=HistoryResponse)
async def get_incident_history_endpoint(
    incident_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get complete audit trail for an incident.

    Shows all state changes, creations, approvals, notifications, etc.
    Sorted chronologically (oldest first).
    """
    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid incident ID format")

    # Verify incident exists
    result = await db.execute(select(Incident).where(Incident.id == incident_uuid))
    incident = result.scalar_one_or_none()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    try:
        history = await get_incident_history(db=db, incident_id=incident_id)
    except Exception as e:
        logger.error(f"Failed to fetch history for {incident_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

    history_entries = [HistoryEntry(**entry) for entry in history]

    return HistoryResponse(
        incident_id=incident