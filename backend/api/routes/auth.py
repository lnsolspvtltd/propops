"""Authentication routes — login + token management."""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Header
from jose import jwt, JWTError
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.auth import revoke_token_jti
from backend.core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


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

    Demo mode: accepts demo credentials only in development/test environments.
    In production, swap this for a real user table lookup.
    """
    if not settings.demo_email or not settings.demo_password:
        logger.error("Missing demo credentials — set DEMO_EMAIL and DEMO_PASSWORD in .env")
        raise HTTPException(
            status_code=503,
            detail={"error": "Demo login not configured"},
        )

    email = req.email.strip().lower()

    if settings.environment == "production":
        raise HTTPException(
            status_code=403,
            detail={"error": "Demo login disabled in production"},
        )

    password_ok = secrets.compare_digest(req.password, settings.demo_password)
    email_ok = email == settings.demo_email.strip().lower()
    if not (email_ok and password_ok):
        raise HTTPException(status_code=401, detail={"error": "Invalid credentials"})

    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {
        "sub": email,
        "email": email,
        "exp": expire,
        "name": email.split("@")[0].title(),
        "jti": str(uuid.uuid4()),
        "org_id": settings.demo_org_id,
        "role": "founder",
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    logger.info("Login: %s", email)
    return LoginResponse(
        access_token=token,
        user={
            "email": email,
            "name": email.split("@")[0].title(),
            "org_id": settings.demo_org_id,
            "role": "founder",
        },
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
async def logout(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke the current token's JTI server-side, then client discards it."""
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            try:
                payload = jwt.decode(
                    parts[1],
                    settings.secret_key,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False},
                )
                jti = payload.get("jti")
                exp = payload.get("exp")
                expires_at = (
                    datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
                )
                if jti:
                    await revoke_token_jti(jti, db, expires_at=expires_at)
            except JWTError:
                logger.warning("Logout: could not decode token for revocation")
    return {"status": "logged_out"}
