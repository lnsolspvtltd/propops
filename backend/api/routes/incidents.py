"""Incidents API routes."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel, ConfigDict
from backend.core.database import get_db
from backend.models.incident import Incident, AIDraft

router = APIRouter()


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    title: str
    category: str
    urgency: str
    status: str
    ai_summary: Optional[str] = None
    ai_confidence: Optional[float] = None
    source_address: Optional[str] = None
    unit_id: Optional[str] = None
    property_id: Optional[str] = None
    created_at: str
    draft_count: int = 0


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
        query = query.where(Incident.status == status)
    if urgency:
        query = query.where(Incident.urgency == urgency)
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
            ai_confidence=inc.ai_confidence,
            source_address=inc.source_address,
            unit_id=str(inc.unit_id) if inc.unit_id else None,
            property_id=str(inc.property_id) if inc.property_id else None,
            created_at=inc.created_at.isoformat() if inc.created_at else "",
            draft_count=len(draft_count_q.scalars().all()),
        ))
    return out


@router.get("/{incident_id}")
async def get_incident(incident_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single incident with all drafts and context."""
    result = await db.execute(select(Incident).where(Incident.id == uuid.UUID(incident_id)))
    inc = result.scalar_one_or_none()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    drafts_q = await db.execute(select(AIDraft).where(AIDraft.incident_id == inc.id))
    drafts = [{"id": str(d.id), "subject": d.subject, "body": d.body, "status": d.status}
              for d in drafts_q.scalars().all()]
    return {
        "id": str(inc.id),
        "title": inc.title,
        "category": inc.category,
        "urgency": inc.urgency,
        "status": inc.status,