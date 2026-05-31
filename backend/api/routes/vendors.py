"""Vendor management CRUD endpoints."""
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.models.vendor import Vendor, VALID_SPECIALTIES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorCreate(BaseModel):
    org_id: uuid.UUID
    name: str
    email: str
    phone: str | None = None
    specialty: str


class VendorOut(BaseModel):
    id: str
    org_id: str
    name: str
    email: str
    phone: str | None
    specialty: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[VendorOut])
async def list_vendors(
    org_id: uuid.UUID,
    specialty: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[VendorOut]:
    """List active vendors, optionally filtered by specialty."""
    stmt = select(Vendor).where(Vendor.org_id == org_id, Vendor.active.is_(True))
    if specialty:
        stmt = stmt.where(Vendor.specialty == specialty)
    result = await db.execute(stmt.order_by(Vendor.name))
    return [VendorOut.model_validate(v) for v in result.scalars().all()]


@router.post("/", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
async def create_vendor(body: VendorCreate, db: AsyncSession = Depends(get_db)) -> VendorOut:
    """Create a new vendor."""
    if body.specialty not in VALID_SPECIALTIES:
        raise HTTPException(
            status_code=422,
            detail={"error": f"specialty must be one of {sorted(VALID_SPECIALTIES)}"},
        )
    vendor = Vendor(
        id=uuid.uuid4(),
        org_id=body.org_id,
        name=body.name,
        email=body.email,
        phone=body.phone,
        specialty=body.specialty,
    )
    db.add(vendor)
    await db.flush()
    return VendorOut.model_validate(vendor)


@router.delete("/{vendor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor(vendor_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    """Soft-delete a vendor (active=False)."""
    res = await db.execute(select(Vendor).where(Vendor.id == vendor_id))
    vendor = res.scalar_one_or_none()
    if vendor is None:
        raise HTTPException(status_code=404, detail={"error": "Vendor not found"})
    vendor.active = False
    await db.flush()
