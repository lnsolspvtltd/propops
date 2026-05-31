"""Unit (tenant_units) management endpoints."""
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.models.tenant import TenantUnit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/units", tags=["units"])


class UnitCreate(BaseModel):
    org_id: uuid.UUID
    label: str
    address: str | None = None


class UnitOut(BaseModel):
    id: str
    org_id: str
    label: str
    address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[UnitOut])
async def list_units(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[UnitOut]:
    result = await db.execute(
        select(TenantUnit).where(TenantUnit.org_id == org_id).order_by(TenantUnit.label)
    )
    return [UnitOut.model_validate(u) for u in result.scalars().all()]


@router.post("/", response_model=UnitOut, status_code=status.HTTP_201_CREATED)
async def create_unit(body: UnitCreate, db: AsyncSession = Depends(get_db)) -> UnitOut:
    unit = TenantUnit(id=uuid.uuid4(), org_id=body.org_id, label=body.label, address=body.address)
    db.add(unit)
    await db.flush()
    return UnitOut.model_validate(unit)
