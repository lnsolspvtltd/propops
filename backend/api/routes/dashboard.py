"""Dashboard stats endpoint — live summary for property managers."""
import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.database import get_db
from backend.models.incident import Incident, AIDraft, Unit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class CategoryCount(BaseModel):
    category: str
    count: int


class RecentIncident(BaseModel):
    id: str
    subject: str
    tenant_name: str | None = None
    unit_label: str | None = None
    urgency: str | None = None
    status: str
    created_at: datetime


class DashboardStats(BaseModel):
    open_incidents: int
    awaiting_approval: int
    resolved_this_week: int
    avg_response_hours: float
    top_categories: list[CategoryCount]
    recent_incidents: list[RecentIncident]


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> DashboardStats:
    """Return live summary stats. Scoped to all orgs (Phase 2 adds org_id filter)."""
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    open_count: int = (await db.execute(
        select(func.count()).select_from(Incident).where(Incident.status != "CLOSED")
    )).scalar_one() or 0

    pending_count: int = (await db.execute(
        select(func.count()).select_from(AIDraft).where(AIDraft.status == "pending")
    )).scalar_one() or 0

    resolved_count: int = (await db.execute(
        select(func.count()).select_from(Incident).where(
            Incident.status == "CLOSED",
            Incident.resolved_at >= week_ago,
        )
    )).scalar_one() or 0

    avg_raw = (await db.execute(
        select(func.avg(func.extract("epoch", AIDraft.sent_at - Incident.created_at) / 3600))
        .select_from(AIDraft)
        .join(Incident, AIDraft.incident_id == Incident.id)
        .where(AIDraft.status == "approved", AIDraft.sent_at.isnot(None))
    )).scalar_one()
    avg_hours = round(float(avg_raw), 1) if avg_raw is not None else 0.0

    cat_rows = (await db.execute(
        select(Incident.category, func.count().label("cnt"))
        .where(Incident.category.isnot(None))
        .group_by(Incident.category)
        .order_by(func.count().desc())
        .limit(5)
    )).all()
    top_categories = [CategoryCount(category=r.category, count=r.cnt) for r in cat_rows]

    recent_rows = (await db.execute(
        select(
            Incident.id, Incident.title, Incident.urgency,
            Incident.status, Incident.created_at,
            Unit.tenant_name, Unit.unit_number.label("unit_label"),
        )
        .outerjoin(Unit, Incident.unit_id == Unit.id)
        .where(Incident.status != "CLOSED")
        .order_by(Incident.created_at.desc())
        .limit(5)
    )).all()
    recent_incidents = [
        RecentIncident(
            id=str(r.id), subject=r.title, tenant_name=r.tenant_name,
            unit_label=r.unit_label, urgency=r.urgency,
            status=r.status, created_at=r.created_at,
        )
        for r in recent_rows
    ]

    return DashboardStats(
        open_incidents=open_count, awaiting_approval=pending_count,
        resolved_this_week=resolved_count, avg_response_hours=avg_hours,
        top_categories=top_categories, recent_incidents=recent_incidents,
    )
