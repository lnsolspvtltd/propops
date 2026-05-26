from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Tenant, Unit

async def resolve_sender(email_address: str, org_id: str) -> dict | None:
    tenant = await get_tenant_by_email_and_org(db, email_address, org_id)
    if not tenant:
        return None

    unit = await get_unit_by_id(db, tenant.unit_id)
    if not unit:
        return None

    return {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "unit_id": unit.id,
        "unit_label": unit.label
    }

async def get_tenant_by_email_and_org(db: AsyncSession, email_address: str, org_id: str) -> Tenant | None:
    return await db.execute(select(Tenant).filter_by(email=email_address, org_id=org_id)).scalar_one_or_none()

async def get_unit_by_id(db: AsyncSession, unit_id: str) -> Unit | None:
    return await db.execute(select(Unit).filter_by(id=unit_id)).scalar_one_or_none()