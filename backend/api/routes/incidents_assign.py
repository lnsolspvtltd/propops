"""Incident assignment and resolution endpoints."""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.models.incident import Incident, Unit
from backend.models.vendor import Vendor
from backend.services.vendor_notifier import notify_vendor

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/incidents", tags=["incidents"])

PM_CONTACT_EMAIL = "hello@propops.app"  # TODO: load from org settings in Phase 3


class AssignRequest(BaseModel):
    vendor_id: uuid.UUID


@router.post("/{incident_id}/assign", status_code=status.HTTP_200_OK)
async def assign_incident(
    incident_id: uuid.UUID,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Assign an incident to a vendor and send notification email."""
    incident = (await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail={"error": "Incident not found"})

    vendor = (await db.execute(
        select(Vendor).where(Vendor.id == body.vendor_id, Vendor.active.is_(True))
    )).scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=404, detail={"error": "Vendor not found or inactive"})

    incident.vendor_id = vendor.id  # type: ignore[attr-defined]
    incident.assigned_at = datetime.now(timezone.utc)  # type: ignore[attr-defined]
    await db.flush()
    await db.commit()

    unit = None
    if incident.unit_id:
        unit = (await db.execute(select(Unit).where(Unit.id == incident.unit_id))).scalar_one_or_none()

    await notify_vendor(
        vendor_email=vendor.email,
        vendor_name=vendor.name,
        incident_title=incident.title,
        incident_summary=incident.ai_summary,
        tenant_name=unit.tenant_name if unit else None,
        unit_label=unit.unit_number if unit else None,
        pm_contact_email=PM_CONTACT_EMAIL,
    )

    return {"status": "assigned", "vendor_id": str(vendor.id), "vendor_name": vendor.name}


@router.post("/{incident_id}/resolve", status_code=status.HTTP_200_OK)
async def resolve_incident(
    incident_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark incident as CLOSED and set resolved_at."""
    incident = (await db.execute(
        select(Incident).where(Incident.id == incident_id)
    )).scalar_one_or_none()
    if incident is None:
        raise HTTPException(status_code=404, detail={"error": "Incident not found"})

    incident.status = "CLOSED"
    incident.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()
    return {"status": "resolved", "incident_id": str(incident_id)}