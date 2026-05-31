"""Resolve inbound sender email to tenant + unit context for AI triage."""
import logging
import uuid
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tenant import Tenant, TenantUnit

logger = logging.getLogger(__name__)


class SenderContext(TypedDict):
    tenant_id: str
    tenant_name: str
    unit_id: str | None
    unit_label: str | None


async def resolve_sender(
    email_address: str,
    org_id: uuid.UUID,
    db: AsyncSession,
) -> SenderContext | None:
    """Return tenant + unit context for an inbound email address.

    Returns None if no active tenant matches — caller decides how to handle unknown senders.
    Never raises; logs and returns None on DB errors.
    """
    email = email_address.strip().lower()
    try:
        res = await db.execute(
            select(Tenant).where(
                Tenant.org_id == org_id,
                Tenant.email == email,
                Tenant.active.is_(True),
            )
        )
        tenant = res.scalar_one_or_none()
    except Exception as e:
        logger.error("context_resolver: DB error for %s: %s", email, e)
        return None

    if tenant is None:
        return None

    unit_label = None
    unit_id_str = None
    if tenant.unit_id:
        ures = await db.execute(select(TenantUnit).where(TenantUnit.id == tenant.unit_id))
        unit = ures.scalar_one_or_none()
        if unit:
            unit_label = unit.label
            unit_id_str = str(unit.id)

    return SenderContext(
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        unit_id=unit_id_str,
        unit_label=unit_label,
    )
