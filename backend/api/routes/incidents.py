"""Incidents API routes."""
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, ConfigDict
from backend.core.database import get_db
from backend.models.incident import Incident, AIDraft

logger = logging.getLogger(__name__)

router = APIRouter()


class IncidentResponse(BaseModel):
    """Response model for incident details."""
    id: str
    title: str
    category: str
    urgency: str
    status: str
    ai_summary: Optional[str] = None
    source_address: Optional[str] = None
    created_at: str
    draft_count: int = 0

    model_config = ConfigDict(from_attributes=True)


@router.get("/", response_model=list[IncidentResponse])
async def list_incidents(
    status: Optional[str] = Query(None),
    urgency: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List incidents with optional filtering by status and urgency.
    
    Args:
        status: Optional status filter (OPEN, CLOSED, etc.)
        urgency: Optional urgency filter (LOW, MEDIUM, HIGH, EMERGENCY)
        limit: Max number of incidents to return (max 200)
        db: Database session
        
    Returns:
        List of incidents with draft counts
    """
    query = select(Incident).order_by(desc(Incident.created_at)).limit(limit)
    if status:
        query = query.where(Incident.status == status)
        logger.debug(f"Filtering incidents by status: {status}")
    if urgency:
        query = query.where(Incident.urgency == urgency)
        logger.debug(f"Filtering incidents by urgency: {urgency}")
    
    result = await db.execute(query)
    incidents = result.scalars().all()
    logger.info(f"Retrieved {len(incidents)} incidents (status={status}, urgency={urgency})")

    out = []
    for inc in incidents:
        draft_count_q = await db.execute(
            select(AIDraft).where(AIDraft.incident_id == inc.id, AIDraft.status == "PENDING_REVIEW")
        )
        draft_count = len(draft_count_q.scalars().all())
        
        response = IncidentResponse(
            id=str(inc.id),
            title=inc.title,
            category=inc.category or "",
            urgency=inc.urgency or "MEDIUM",
            status=inc.status or "OPEN",
            ai_summary=inc.ai_summary,
            source_address=inc.source_address,
            created_at=inc.created_at.isoformat() if inc.created_at else "",
            draft_count=draft_count,
        )
        out.append(response)
    
    return out


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a single incident with all associated drafts.
    
    Args:
        incident_id: UUID of incident
        db: Database session
        
    Returns:
        Incident details with draft list
        
    Raises:
        HTTPException: 404 if incident not found
        HTTPException: 422 if incident_id format invalid
    """
    try:
        incident_uuid = uuid.UUID(incident_id)
    except ValueError:
        logger.warning(f"Invalid incident_id format attempted: {incident_id!r}")
        raise HTTPException(status_code=422, detail=f"Invalid incident_id format: {incident_id!r}")
    
    result = await db.execute(select(Incident).where(Incident.id == incident_uuid))
    inc = result.scalar_one_or_none()
    if not inc:
        logger.warning(f"Incident not found: {incident_id}")
        raise HTTPException(status_code=404, detail="Incident not found")
    
    drafts_q = await db.execute(select(AIDraft).where(AIDraft.incident_id == inc.id))
    drafts = [
        {"id": str(d.id), "draft_text": d.draft_text, "status": d.status,
         "created_at": d.created_at.isoformat() if d.created_at else None}
        for d in drafts_q.scalars().all()
    ]
    
    logger.info(f"Retrieved incident {incident_id} with {len(drafts)} drafts")
    
    return {
        "id": str(inc.id), "title": inc.title, "category": inc.category,
        "urgency": inc.urgency, "status": inc.status, "summary": inc.ai_summary,
        "source": inc.source_address, "raw_message": inc.raw_message,
        "created_at": inc.created_at.isoformat() if inc.created_at else "", "drafts": drafts,
    }
