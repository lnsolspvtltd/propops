"""Org member invite routes (admin-only)."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.auth import assert_org, get_current_user, revoke_token_jti
from backend.core.config import settings
from backend.core.database import get_db
from backend.models.invite import Invite
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/orgs", tags=["invites"])

INVITE_EXPIRE_HOURS = 72


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = "member"

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("role")
    @classmethod
    def valid_role(cls, v: str) -> str:
        if v not in ("admin", "member"):
            raise ValueError("role must be 'admin' or 'member'")
        return v


class InviteOut(BaseModel):
    invite_id: str
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


def _require_admin(user: dict[str, Any]) -> None:
    if user.get("role") not in ("admin", "founder"):
        raise HTTPException(403, {"error": "admin_required"})


def _make_invite_token(email: str, org_id: str, role: str, jti: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRE_HOURS)
    payload = {
        "sub": email,
        "org_id": org_id,
        "role": role,
        "purpose": "invite",
        "jti": jti,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


@router.post("/{org_id}/invites", response_model=InviteOut, status_code=201)
async def create_invite(
    org_id: uuid.UUID,
    body: InviteCreate,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InviteOut:
    """Create an invite link for a new org member. Admin only."""
    assert_org(user, org_id)
    _require_admin(user)

    # Check email not already an active user in this org
    existing = (await db.execute(
        select(User).where(User.email == body.email, User.org_id == org_id)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(409, {"error": "user_already_exists", "message": "Email already has an account in this org"})

    jti = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRE_HOURS)

    # Get created_by user id if available (may be demo user with sentinel UUID)
    try:
        created_by = uuid.UUID(user["id"])
        # Verify the user actually exists in DB; demo sentinel won't
        user_row = (await db.execute(select(User).where(User.id == created_by))).scalar_one_or_none()
        if not user_row:
            created_by = None
    except (ValueError, KeyError):
        created_by = None

    invite = Invite(
        org_id=org_id,
        email=body.email,
        role=body.role,
        jti=jti,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    # Build and log invite link (in production this would be emailed)
    invite_token = _make_invite_token(body.email, str(org_id), body.role, jti)
    invite_url = f"{settings.frontend_url}/accept-invite?token={invite_token}"
    logger.info("invite created: id=%s email=%s org=%s url=%s", invite.id, body.email, org_id, invite_url)

    # TODO: send invite email via BackgroundTasks — skipped here to keep route simple;
    # add when email service is configured for transactional sends.

    return InviteOut(
        invite_id=str(invite.id),
        email=invite.email,
        role=invite.role,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
    )


@router.get("/{org_id}/invites", response_model=list[InviteOut])
async def list_invites(
    org_id: uuid.UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InviteOut]:
    """List pending (not yet accepted) invites for an org. Admin only."""
    assert_org(user, org_id)
    _require_admin(user)

    result = await db.execute(
        select(Invite)
        .where(Invite.org_id == org_id, Invite.accepted_at.is_(None))
        .order_by(Invite.created_at.desc())
    )
    invites = result.scalars().all()
    return [
        InviteOut(
            invite_id=str(i.id),
            email=i.email,
            role=i.role,
            expires_at=i.expires_at,
            created_at=i.created_at,
        )
        for i in invites
    ]


@router.delete("/{org_id}/invites/{invite_id}", status_code=204)
async def revoke_invite(
    org_id: uuid.UUID,
    invite_id: uuid.UUID,
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a pending invite. Admin only. Adds JTI to blocklist."""
    assert_org(user, org_id)
    _require_admin(user)

    result = await db.execute(select(Invite).where(Invite.id == invite_id, Invite.org_id == org_id))
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(404, {"error": "invite_not_found"})
    if invite.accepted_at:
        raise HTTPException(409, {"error": "invite_already_accepted"})

    # Revoke JTI to invalidate the invite link
    await revoke_token_jti(invite.jti, db, expires_at=invite.expires_at)
    await db.delete(invite)
    await db.commit()
