from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .models import Organisation
from .core.encryption import encrypt
from .services.inbox_poller import poll_imap
from .config import get_db

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

class SetupRequest(BaseModel):
    name: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password_enc: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password_enc: str

@router.post("/setup", response_model=OrganisationResponse)
async def setup_org(
    request: SetupRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Encrypt passwords
        encrypted_imap_password = encrypt(request.imap_password_enc)
        encrypted_smtp_password = encrypt(request.smtp_password_enc)

        # Create organisation
        new_org = Organisation(
            name=request.name,
            imap_host=request.imap_host,
            imap_port=request.imap_port,
            imap_username=request.imap_username,
            imap_password=encrypted_imap_password,
            smtp_host=request.smtp_host,
            smtp_port=request.smtp_port,
            smtp_username=request.smtp_username,
            smtp_password=encrypted_smtp_password,
            polling_active=True
        )
        db.add(new_org)
        await db.commit()
        await db.refresh(new_org)

        # Test IMAP connection
        if not await poll_imap(request.imap_host, request.imap_port, request.imap_username, encrypted_imap_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Cannot connect to IMAP: "}
            )

        return OrganisationResponse(**new_org.__dict__)
    except Exception as e:
        logger.exception(f"Failed to setup organisation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Internal server error"}
        )

@router.get("/status", response_model=OrganisationResponse)
async def get_org_status(org_id: str, db: AsyncSession = Depends(get_db)):
    org = await db.execute(select(Organisation).where(Organisation.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Organisation not found"}
        )
    return OrganisationResponse(**org.__dict__)

@router.post("/test-imap", response_model=OrganisationResponse)
async def test_imap_connection(
    request: SetupRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        # Encrypt passwords
        encrypted_imap_password = encrypt(request.imap_password_enc)

        # Test IMAP connection
        if not await poll_imap(request.imap_host, request.imap_port, request.imap_username, encrypted_imap_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Cannot connect to IMAP: "}
            )

---

#### FILE: backend/core/encryption.py
---
from cryptography.fernet import Fernet
import os

def encrypt(plaintext: str) -> str:
    """Encrypt plaintext using Fernet."""
    key = os.getenv('FERNET_KEY')
    if not key:
        raise ValueError("FERNET_KEY environment variable is missing.")
    
    f = Fernet(key)
    encrypted = f.encrypt(plaintext.encode())
    return encrypted.decode()

def decrypt(ciphertext: str) -> str:
    """Decrypt ciphertext using Fernet."""
    key = os.getenv('FERNET_KEY')
    if not key:
        raise ValueError("FERNET_KEY environment variable is missing.")
    
    f = Fernet(key)
    decrypted = f.decrypt(ciphertext.encode())
    return decrypted.decode()
---

#### FILE: backend/models/organisation.py
---
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
import logging

logger = logging.getLogger(__name__)

class Organisation(Base):
    __tablename__ = "organisations"
    
    id: Mapped[str] = mapped_column(primary_key=True)
    name: str = mapped_column(String(255), nullable=False)
    imap_host: str | None = mapped_column(String(255))
    imap_port: int = mapped_column(Integer, default=993)
    imap_username: str | None = mapped_column(String(255))
    imap_password_enc: str | None = mapped_column(String(255))  # Fernet encrypted
    smtp_host: str | None = mapped_column(String(255))
    smtp_port: int = mapped_column(Integer, default=587)
    polling_active: bool = mapped_column(Boolean, default=False)
    created_at: Mapped[DateTime] = mapped_column(default=DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[DateTime] = mapped_column(default=DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    # Indexes
    __table_args__ = (
        Index("idx_organisations_deleted", deleted_at),
    )

    def __repr__(self):
        return f"<Organisation(id={self.id}, name={self.name})>"
---