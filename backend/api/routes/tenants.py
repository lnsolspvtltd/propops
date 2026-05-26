from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_db
from backend.models import Tenant, Unit
from backend.services.context_resolver import resolve_sender

router = APIRouter(prefix="/api/v1", tags=["tenants"])

class TenantCreate(BaseModel):
    name: str
    email: str
    phone: str | None
    unit_id: str | None

class TenantBulkUploadRequest(BaseModel):
    file: UploadFile

@router.get("/tenants")
async def list_tenants(db: AsyncSession = Depends(get_db)):
    tenants = await db.execute(select(Tenant).filter_by(deleted_at=None))
    return {"tenants": [tenant.model_dump() for tenant in tenants.scalars().all()]}

@router.post("/tenants")
async def create_tenant(tenant_data: TenantCreate, db: AsyncSession = Depends(get_db)):
    try:
        unit = await db.execute(select(Unit).filter_by(id=tenant_data.unit_id)).scalar_one_or_none()
        if not unit:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unit not found")

        tenant = Tenant(
            name=tenant_data.name,
            email=tenant_data.email,
            phone=tenant_data.phone,
            unit_id=tenant_data.unit_id
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)

        return {"id": tenant.id, "name": tenant.name}
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.post("/tenants/bulk")
async def bulk_upload_tenants(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    tenants_created = 0
    tenants_skipped = 0
    errors = []

    try:
        # Parse CSV file
        import csv
        reader = csv.DictReader(file.file)
        for row in reader:
            try:
                unit = await db.execute(select(Unit).filter_by(label=row['unit_label'], org_id=row['org_id'])).scalar_one_or_none()
                if not unit:
                    errors.append({"email": row['email'], "error": "Unit not found"})
                    continue

                tenant = Tenant(
                    name=row['name'],
                    email=row['email'],
                    phone=row['phone'],
                    unit_id=unit.id
                )
                db.add(tenant)
                tenants_created += 1
            except ValidationError as e:
                errors.append({"email": row['email'], "error": str(e)})
            except Exception as e:
                errors.append({"email": row['email'], "error": str(e)})

        await db.commit()
    except Exception as e:
        errors.append({"email": None, "error": str(e)})

    return {
        "created": tenants_created,
        "skipped": tenants_skipped,
        "errors": errors
    }

@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    tenant = await db.execute(select(Tenant).filter_by(id=tenant_id)).scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.deleted_at = sa.func.now()
    await db.commit()

    return {"id": tenant.id}