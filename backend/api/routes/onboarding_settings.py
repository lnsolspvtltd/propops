"""Organisation settings update endpoint (Phase 3 addition)."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.encryption import encrypt
from backend.models.organisation import Organisation
from backend.api.routes.onboarding import _check_imap, OrganisationResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class SettingsUpdate(BaseModel):
    imap_host: str | None = None
    imap_port: int | None = None
    imap_username: str | None = None
    imap_password: str | None = None   # plaintext — encrypted before storage
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    polling_active: bool | None = None


@router.put("/settings", response_model=OrganisationResponse)
async def update_settings(
    org_id: str,
    body: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrganisationResponse:
    """Partial update of org IMAP/SMTP settings. Re-tests IMAP if credentials changed."""
    try:
        oid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "Invalid org_id"})

    res = await db.execute(select(Organisation).where(Organisation.id == oid))
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail={"error": "Organisation not found"})

    creds_changed = body.imap_password or body.imap_host or body.imap_username
    if creds_changed:
        host = body.imap_host or org.imap_host or ""
        port = body.imap_port or org.imap_port or 993
        user = body.imap_username or org.imap_username or ""
        pwd = body.imap_password or ""
        if pwd:
            ok, err = _check_imap(host, port, user, pwd)
            if not ok:
                raise HTTPException(status_code=400, detail={"error": f"IMAP test failed: {err}"})

    if body.imap_host is not None: org.imap_host = body.imap_host
    if body.imap_port is not None: org.imap_port = body.imap_port
    if body.imap_username is not None: org.imap_username = body.imap_username
    if body.imap_password: org.imap_password_enc = encrypt(body.imap_password)
    if body.smtp_host is not None: org.smtp_host = body.smtp_host
    if body.smtp_port is not None: org.smtp_port = body.smtp_port
    if body.smtp_username is not None: org.smtp_username = body.smtp_username
    if body.smtp_password: org.smtp_password_enc = encrypt(body.smtp_password)
    if body.polling_active is not None: org.polling_active = body.polling_active

    await db.flush()
    return OrganisationResponse(org_id=str(org.id), name=org.name,
                                polling_active=org.polling_active, imap_connected=True)
