"""Incidents API routes."""
import uuid
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, ConfigDict, field_validator
from backend.core.database import get_db
from backend.models.incident import Incident, AIDraft
from backend.services.incident_state_service import (
    transition_incident_status,
    get_incident_history,
    StateTransitionError,
)
from backend.core.state_machine import get_valid_transitions, IncidentStatus, validate_transition
from backend.api.auth import get_current_user, require_role, User

logger = logging.getLogger(__name__)

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
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    draft_count: int = 0


class StatusChangeRequest(BaseModel):
    """Request body for PATCH /incidents/{id}/status."""
    new_status: str
    reason: Optional[str] = None
    allow_override: bool = False
    
    # SECURITY-REVIEW: Validate new_status against enum before state machine call
    @field_validator("new_status")
    @classmethod
    def validate_new_status(cls, v: str) -> str:
        """Validate new_status is a known enum value."""
        valid_statuses = {s.value for s in IncidentStatus}
        if v.upper() not in valid_statuses:
            raise ValueError(f"new_status must be one of {valid_statuses}")
        return v.upper()


class StatusChangeResponse(BaseModel):
    """Response after status change."""
    incident_id: str
    from_status: str
    to_status: str
    changed: bool
    timestamp: datetime
    valid_next_states: list[str]


class HistoryEntry(BaseModel):
    """Single audit log entry."""
    id: str
    action: str
    actor: str
    details: dict
    created_at: datetime


class HistoryResponse(BaseModel):
    """Full incident history."""
    incident_id: str
    history: list[HistoryEntry]


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    status: Optional[str] = Query(None),
    urgency: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List incidents with optional filtering. Requires authentication."""
    logger.info(f"User {user.email} listing incidents (status={status}, urgency={urgency})")
    
    query = select(Incident).order_by(desc(Incident.created_at)).limit(limit)
    if status:
        query = query.where(Incident.status == status.upper())
    if urgency:
        query = query.where(Incident.urgency == urgency.upper())
    
    result = await db.execute(query)
    incidents = result.scalars().all()
    logger.info(f"Retrieved {len(incidents)} incidents (status={status}, urgency={urgency})")

    out = []
    for inc in incidents:
        draft_count_q = await db.execute(
            select(AIDraft).where(AIDraft.incident_id == inc.id, AIDraft.status == "PENDING_REVIEW")
        )
        draft_count = len(draft_count_q.scalars().all())
        
        out.append(IncidentResponse(
            id=str(inc.id),
            title=inc.title,
            category=inc.category or "",
            urgency=inc.urgency or "MEDIUM",
            status=inc.status or "OPEN",
            ai_summary=inc.ai_summary,
            source_address=inc.source_address,
            created_at=inc.created_at,
            updated_at=inc.updated_at,
            resolved_at=inc.resolved_at if hasattr(inc, 'resolved_at') else None,
            draft_count=draft_count,
        ))
    
    return out


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single incident by ID. Requires authentication."""
    logger.info(f"User {user.email} fetching incident {incident_id}")
    
    try:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
    except ValueError:
        logger.warning(f"Invalid incident_id format: {incident_id}")
        raise HTTPException(status_code=400, detail="Invalid incident ID format")
    
    incident = result.scalar_one_or_none()
    if not incident:
        logger.warning(f"Incident {incident_id} not found")
        raise HTTPException(status_code=404, detail="Incident not found")
    
    draft_count_q = await db.execute(
        select(AIDraft).where(AIDraft.incident_id == incident.id, AIDraft.status == "pending")
    )
    draft_count = len(draft_count_q.scalars().all())
    
    return IncidentResponse(
        id=str(incident.id),
        title=incident.title,
        category=incident.category or "",
        urgency=incident.urgency or "MEDIUM",
        status=incident.status or "OPEN",
        ai_summary=incident.ai_summary,
        source_address=incident.source_address,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        resolved_at=incident.resolved_at if hasattr(incident, 'resolved_at') else None,
        draft_count=draft_count,
    )


@router.patch("/{incident_id}/status", response_model=StatusChangeResponse)
async def change_incident_status(
    incident_id: str,
    req: StatusChangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change incident status with state machine validation.
    
    SECURITY-REVIEW: Actor is derived from authenticated JWT token (user.email),
    not from request body. Cannot be spoofed. Authorization checks enforce that
    only admins can use allow_override=True.
    
    Input validation:
    - new_status validated against enum in StatusChangeRequest
    - allow_override gated behind admin role check
    """
    logger.info(
        f"User {user.email} (role={user.role}) requesting status change for incident {incident_id}: "
        f"{req.new_status}, override={req.allow_override}"
    )
    
    try:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
    except ValueError:
        logger.warning(f"Invalid incident_id format: {incident_id}")
        raise HTTPException(status_code=400, detail="Invalid incident ID format")
    
    incident = result.scalar_one_or_none()
    if not incident:
        logger.warning(f"Incident {incident_id} not found")
        raise HTTPException(status_code=404, detail="Incident not found")
    
    # SECURITY-REVIEW: Only admin can use allow_override
    if req.allow_override and user.role != "admin":
        logger.warning(f"Non-admin user {user.email} attempted to use allow_override flag")
        raise HTTPException(
            status_code=403,
            detail="allow_override requires admin role"
        )
    
    current_status = incident.status or "OPEN"
    
    # Validate transition
    is_valid, error_msg = validate_transition(
        current_status=current_status,
        new_status=req.new_status,
        allow_override=req.allow_override,
    )
    
    if not is_valid:
        logger.warning(f"Invalid transition: {current_status} → {req.new_status}: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Apply transition
    old_status = incident.status
    incident.status = req.new_status
    incident.updated_at = datetime.now(timezone.utc)
    
    try:
        await db.commit()
        logger.info(
            f"Incident {incident_id} status changed {old_status} → {req.new_status} by {user.email}. "
            f"Reason: {req.reason or '(none)'}"
        )
        
        valid_next = list(get_valid_transitions(req.new_status))
        return StatusChangeResponse(
            incident_id=incident_id,
            from_status=old_status,
            to_status=req.new_status,
            changed=True,
            timestamp=incident.updated_at,
            valid_next_states=valid_next,
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Error changing incident status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error — see logs")


@router.get("/{incident_id}/history", response_model=HistoryResponse)
async def get_incident_history(
    incident_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get full audit history for an incident. Requires authentication."""
    logger.info(f"User {user.email} fetching history for incident {incident_id}")
    
    try:
        result = await db.execute(
            select(Incident).where(Incident.id == uuid.UUID(incident_id))
        )
    except ValueError:
        logger.warning(f"Invalid incident_id format: {incident_id}")
        raise HTTPException(status_code=400, detail="Invalid incident ID format")
    
    incident = result.scalar_one_or_none()
    if not incident:
        logger.warning(f"Incident {incident_id} not found")
        raise HTTPException(status_code=404, detail="Incident not found")
    
    # TODO: Implement audit log fetching from audit_logs table
    return HistoryResponse(
        incident_id=incident_id,
        history=[],
    )

