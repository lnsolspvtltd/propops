"""Tenant management endpoints (list, create, bulk CSV upload, soft-delete)."""
import csv
import io
import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import assert_org, get_current_user
from backend.core.database import get_db
from backend.models.tenant import Tenant, TenantUnit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenants", tags=["tenants"])


class TenantCreate(BaseModel):
    name: str
    email: str
    phone: str | None = None
    unit_id: uuid.UUID | None = None


class TenantOut(BaseModel):
    id: str
    org_id: str
    name: str
    email: str
    phone: str | None
    unit_id: str | None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class BulkResult(BaseModel):
    created: int
    skipped: int
    errors: list[str]


@router.get("/", response_model=list[TenantOut])
async def list_tenants(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TenantOut]:
    """List active tenants for the authenticated user's org."""
    org_id = uuid.UUID(user["org_id"])
    offset = (page - 1) * page_size
    result = await db.execute(
        select(Tenant)
        .where(Tenant.org_id == org_id, Tenant.active.is_(True))
        .order_by(Tenant.name)
        .offset(offset)
        .limit(page_size)
    )
    return [TenantOut.model_validate(t) for t in result.scalars().all()]


@router.post("/", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantOut:
    """Create a single tenant scoped to the authenticated user's org."""
    org_id = uuid.UUID(user["org_id"])
    tenant = Tenant(
        id=uuid.uuid4(),
        org_id=org_id,
        name=body.name,
        email=body.email.strip().lower(),
        phone=body.phone,
        unit_id=body.unit_id,
    )
    db.add(tenant)
    await db.flush()
    return TenantOut.model_validate(tenant)


@router.post("/bulk", response_model=BulkResult)
async def bulk_upload(
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BulkResult:
    """Upload tenants via CSV. Columns: name,email,phone,unit_label,unit_address."""
    org_id = uuid.UUID(user["org_id"])
    created = skipped = 0
    errors: list[str] = []
    try:
        content = await file.read()
        reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    except Exception as e:
        raise HTTPException(status_code=400, detail={"error": f"Cannot parse CSV: {e}"})

    for i, row in enumerate(reader, start=2):
        try:
            email = (row.get("email") or "").strip().lower()
            name = (row.get("name") or "").strip()
            if not email or not name:
                errors.append(f"Row {i}: missing name or email")
                skipped += 1
                continue

            unit_id = None
            label = (row.get("unit_label") or "").strip()
            if label:
                ures = await db.execute(
                    select(TenantUnit).where(TenantUnit.org_id == org_id, TenantUnit.label == label)
                )
                unit = ures.scalar_one_or_none()
                if unit is None:
                    unit = TenantUnit(
                        id=uuid.uuid4(), org_id=org_id, label=label,
                        address=(row.get("unit_address") or "").strip() or None,
                    )
                    db.add(unit)
                    await db.flush()
                unit_id = unit.id

            existing = (await db.execute(
                select(Tenant).where(Tenant.org_id == org_id, Tenant.email == email)
            )).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            db.add(Tenant(
                id=uuid.uuid4(), org_id=org_id, name=name, email=email,
                phone=(row.get("phone") or "").strip() or None,
                unit_id=unit_id,
            ))
            created += 1
        except Exception as e:
            errors.append(f"Row {i}: {e}")
            skipped += 1

    await db.flush()
    return BulkResult(created=created, skipped=skipped, errors=errors)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: uuid.UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Soft-delete a tenant (active=False). Enforces org ownership."""
    org_id = uuid.UUID(user["org_id"])
    res = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    t = res.scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=404, detail={"error": "Tenant not found"})
    assert_org(user, t.org_id)
    t.active = False
    await db.flush()
