from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from .db import get_db
from .models import Organization, Property, Unit, Incident, AI_Draft
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

class DashboardStats(BaseModel):
    open_incidents: int
    awaiting_approval: int
    resolved_this_week: int
    avg_response_hours: float
    top_categories: list[dict[str, str]]
    recent_incidents: list[dict[str, str]]

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    open_incidents = await db.execute(
        select(func.count(Incident.id)).where(Incident.status != "closed")
    ).scalar_one_or_none()
    
    awaiting_approval = await db.execute(
        select(func.count(AI_Draft.id)).where(AI_Draft.status == "pending")
    ).scalar_one_or_none()

    resolved_this_week = await db.execute(
        select(func.count(Incident.id)).where(
            Incident.status == "closed",
            Incident.resolved_at >= datetime.datetime.now() - timedelta(days=7)
        )
    ).scalar_one_or_none()

    avg_response_hours = await db.execute(
        select(func.avg((AI_Draft.approved_at - Incident.created_at).total_seconds() / 3600))
        .where(AI_Draft.status == "approved")
    ).scalar_one_or_none()

    top_categories = (
        await db.execute(
            select(Incident.category, func.count(Incident.id))
            .group_by(Incident.category)
            .order_by(func.count(Incident.id).desc())
            .limit(5)
        )
    ).mappings().all()
    
    recent_incidents = (
        await db.execute(
            select(
                Incident.id,
                Incident.title,
                Unit.tenant_name,
                Unit.unit_label,
                Incident.urgency
            )
            .join(Unit, Incident.unit_id == Unit.id)
            .where(Incident.status == "open")
            .order_by(Incident.created_at.desc())
            .limit(5)
        )
    ).mappings().all()

    return DashboardStats(
        open_incidents=open_incidents or 0,
        awaiting_approval=awaiting_approval or 0,
        resolved_this_week=resolved_this_week or 0,
        avg_response_hours=avg_response_hours or 0.0,
        top_categories=[{"category": category, "count": count} for category, count in top_categories],
        recent_incidents=[
            {
                "id": incident.id,
                "subject": incident.title,
                "tenant_name": unit.tenant_name,
                "unit_label": unit.unit_label,
                "urgency": incident.urgency
            }
            for incident, unit in zip(recent_incidents, units)
        ]
    )

---