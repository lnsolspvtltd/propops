"""Authentication routes — login + token management."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

Real user auth backed by the `users` table.  bcrypt password hashing via
passlib.  JWT tokens include sub, email, org_id, role, and jti claims.

Demo-credential fallback is gated by settings.enable_demo_login and is
disabled automatically in production regardless of that flag.
"""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.models.organisation import Organisation
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Stable sentinel UUID for demo JWT "sub" claim — not a real user UUID
_DEMO_SUB = "00000000-0000-0000-0000-000000000099"

# bcrypt context — auto-handles future algorithm migrations
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-computed bcrypt hash at cost 12 — used for constant-time dummy verification
# to prevent email enumeration via response time. The plaintext is irrelevant.
_DUMMY_HASH = "$2b$12$eixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Payload for POST /register."""

    email: EmailStr  # validates RFC 5322 format
    password: str
    org_id: uuid.UUID
    role: Literal["member", "manager"] = "member"  # admin only via invite/migration

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class RegisterResponse(BaseModel):
    """Registration success — never includes the password."""

    id: uuid.UUID
    email: str
    org_id: uuid.UUID
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    org_id: uuid.UUID

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_token(user: User) -> str:
    """Build a signed JWT for *user*.

    Claims:
    - sub   — str(user.id)
    - email — user.email
    - org_id — str(user.org_id)
    - role  — user.role
    - jti   — fresh UUID4 (allows future revocation)
    - exp   — jwt_access_token_expire_minutes from now
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "org_id": str(user.org_id),
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": email,
        "exp": expire,
        "name": email.split("@")[0].title(),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Create a new user account.

    Checks:
    - org_id must reference an existing Organisation (404 otherwise)
    - email must be unique within the org (409 otherwise)
    - password is hashed with bcrypt before persistence
    """
    # 1. Verify org exists
    org_result = await db.execute(
        select(Organisation).where(Organisation.id == req.org_id)
    )
    org = org_result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "org_not_found", "message": "Organisation not found"},
        )

    # 2. Hash password — the plaintext is discarded immediately
    hashed = pwd_context.hash(req.password)

    # 3. Persist — IntegrityError handles duplicate email (including TOCTOU race)
    new_user = User(
        org_id=req.org_id,
        email=req.email,
        hashed_password=hashed,
        role=req.role,
        email_verified=False,
    )
    try:
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"error": "email_already_registered"},
        )

    logger.info("register: new user id=%s email=%s org=%s", new_user.id, new_user.email, new_user.org_id)
    return RegisterResponse(
        id=new_user.id,
        email=new_user.email,
        org_id=new_user.org_id,
        role=new_user.role,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate and return a JWT.

    Primary path: look up the user in the `users` table by email, verify the
    bcrypt hash, and issue a token.

    Demo fallback: if settings.enable_demo_login is True **and** the
    environment is not production, the configured demo credentials are accepted
    as a secondary path so existing development workflows keep working.
    Demo path only accepts the exact configured demo_email — not any email.
    """
    email = req.email  # already lowercased by LoginRequest.email_lowercase validator

    # ------------------------------------------------------------------
    # Real user table lookup (primary path) — scoped by email AND org_id
    # SECURITY: both columns required to prevent cross-tenant auth in multi-tenant DB
    # ------------------------------------------------------------------
    user_result = await db.execute(
        select(User).where(User.email == email, User.org_id == req.org_id)
    )
    db_user = user_result.scalar_one_or_none()

    if db_user is not None:
        # Always run bcrypt first — checking email_verified before verify() creates a
        # timing oracle that leaks "email exists but unverified" to attackers.
        try:
            password_ok = pwd_context.verify(req.password, db_user.hashed_password)
        except Exception:
            password_ok = False

        # Check verified AFTER bcrypt so both failure paths return 401 at the same latency.
        # Return generic invalid_credentials — never expose "email exists but unverified"
        # to unauthenticated callers (response-body oracle). Log internally for observability.
        if not db_user.email_verified:
            logger.warning("login: unverified email for user id=%s", db_user.id)
            raise HTTPException(status_code=401, detail={"error": "invalid_credentials"})

        if not password_ok:
            logger.warning("login: wrong password for email=%s", email)
            raise HTTPException(status_code=401, detail={"error": "invalid_credentials"})

        token = _make_token(db_user)
        logger.info("login: user id=%s email=%s org=%s", db_user.id, db_user.email, db_user.org_id)
        return LoginResponse(
            access_token=token,
            user={
                "id": str(db_user.id),
                "email": db_user.email,
                "org_id": str(db_user.org_id),
                "role": db_user.role,
            },
        )

    # Dummy bcrypt verify to consume constant time when user not found (prevents email enumeration)
    try:
        pwd_context.verify(req.password, _DUMMY_HASH)  # constant-time guard; result discarded
    except Exception:
        pass  # never propagate — timing oracle protection only

    # ------------------------------------------------------------------
    # Demo-credential fallback (non-production only)
    # ------------------------------------------------------------------
    if (
        settings.enable_demo_login
        and settings.environment != "production"
        and settings.demo_email
        and settings.demo_password
    ):
        # demo_org_id must be configured — refuse to issue org_id=None tokens
        if not settings.demo_org_id:
            logger.error("Demo login missing demo_org_id configuration")
            raise HTTPException(status_code=503, detail={"error": "service_unavailable"})

        email_ok = secrets.compare_digest(email, settings.demo_email.strip().lower())
        pass_ok = secrets.compare_digest(req.password, settings.demo_password)
        if email_ok and pass_ok:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
            payload = {
                "sub": _DEMO_SUB,  # stable sentinel UUID — NOT a real user UUID
                "email": settings.demo_email,
                "org_id": str(settings.demo_org_id),
                "role": "founder",  # not "admin" — demo role is "founder"
                "jti": str(uuid.uuid4()),
                "exp": expire,
                "name": settings.demo_email.split("@")[0].title(),
            }
            token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
            logger.info("login: demo session for email=%s", settings.demo_email)
            return LoginResponse(
                access_token=token,
                user={
                    "email": settings.demo_email,
                    "name": settings.demo_email.split("@")[0].title(),
                    "role": "founder",
                    "org_id": str(settings.demo_org_id),
                },
            )

    # No match in users table and demo fallback didn't apply
    raise HTTPException(status_code=401, detail={"error": "invalid_credentials"})


@router.post("/logout")
async def logout() -> dict:
    """Client must discard the token. Server is stateless for now."""
    return {"status": "logged_out"}
