"""Organisation onboarding — IMAP setup wizard endpoints."""
import imaplib
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.core.encryption import decrypt, encrypt
from backend.models.organisation import Organisation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


class SetupRequest(BaseModel):
    org_name: str
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str


class TestImapRequest(BaseModel):
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str


class OrganisationResponse(BaseModel):
    org_id: str
    name: str
    polling_active: bool
    imap_connected: bool


def _check_imap(host: str, port: int, user: str, pwd: str) -> tuple[bool, str]:
    """Test IMAP connection. Returns (success, error_message)."""
    try:
        with imaplib.IMAP4_SSL(host, port) as m:
            m.login(user, pwd)
        return True, ""
    except imaplib.IMAP4.error as e:
        return False, str(e)
    except OSError as e:
        return False, f"Connection error: {e}"
    except Exception as e:
        return False, str(e)


@router.post("/test-imap")
async def test_imap_connection(req: TestImapRequest) -> dict:
    """Test IMAP credentials without persisting anything."""
    ok, err = _check_imap(req.imap_host, req.imap_port, req.imap_username, req.imap_password)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": f"Cannot connect to IMAP: {err}"})
    return {"status": "ok"}


@router.post("/setup", response_model=OrganisationResponse, status_code=status.HTTP_201_CREATED)
async def setup_org(req: SetupRequest, db: AsyncSession = Depends(get_db)) -> OrganisationResponse:
    """Create organisation after verifying IMAP connection.

    IMAP is tested BEFORE any DB write to prevent orphan rows on bad credentials.
    Passwords are Fernet-encrypted before storage — never stored in plaintext.
    """
    ok, err = _check_imap(req.imap_host, req.imap_port, req.imap_username, req.imap_password)
    if not ok:
        raise HTTPException(status_code=400, detail={"error": f"Cannot connect to IMAP: {err}"})

    try:
        org = Organisation(
            id=uuid.uuid4(),
            name=req.org_name,
            imap_host=req.imap_host,
            imap_port=req.imap_port,
            imap_username=req.imap_username,
            imap_password_enc=encrypt(req.imap_password),
            smtp_host=req.smtp_host,
            smtp_port=req.smtp_port,
            smtp_username=req.smtp_username,
            smtp_password_enc=encrypt(req.smtp_password),
            polling_active=True,
        )
        db.add(org)
        await db.flush()
        return OrganisationResponse(
            org_id=str(org.id), name=org.name,
            polling_active=True, imap_connected=True,
        )
    except Exception as e:
        logger.exception("Failed to save organisation")
        raise HTTPException(status_code=500, detail={"error": "Failed to save organisation"}) from e


@router.get("/status", response_model=OrganisationResponse)
async def org_status(org_id: str, db: AsyncSession = Depends(get_db)) -> OrganisationResponse:
    """Return current onboarding status for an organisation."""
    try:
        oid = uuid.UUID(org_id)
    except ValueError:
        raise HTTPException(status_code=400, detail={"error": "Invalid org_id"})

    res = await db.execute(select(Organisation).where(Organisation.id == oid))
    org = res.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail={"error": "Organisation not found"})

    imap_ok = False
    if org.imap_host and org.imap_username and org.imap_password_enc:
        try:
            imap_ok, _ = _check_imap(
                org.imap_host, org.imap_port,
                org.imap_username, decrypt(org.imap_password_enc),
            )
        except Exception:
            pass

    return OrganisationResponse(
        org_id=str(org.id), name=org.name,
        polling_active=org.polling_active, imap_connected=imap_ok,
    )
