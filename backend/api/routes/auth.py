"""Authentication routes — register, login, logout, email verification, password reset."""
import logging
import secrets
import smtplib
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, Response
from jose import jwt, JWTError
from jose.exceptions import ExpiredSignatureError
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.auth import revoke_token_jti, is_jti_revoked
from backend.core.database import get_db
from backend.models.invite import Invite
from backend.models.organisation import Organisation
from backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Precomputed hash to consume constant time when user not found (prevents email enumeration)
_DUMMY_HASH = "$2b$12$dummyhashfortimingguardXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
# Stable sentinel sub for demo tokens — NOT a real user UUID
_DEMO_SUB = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    org_id: uuid.UUID
    role: str = "member"

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class RegisterResponse(BaseModel):
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


class EmailVerifyRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr
    org_id: uuid.UUID

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    org_id: uuid.UUID

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class AcceptInviteRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(user: User) -> str:
    """Create a signed access JWT for a real user row."""
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


def _make_purpose_token(sub: str, purpose: str, exp_hours: int, extra: dict | None = None) -> tuple[str, str]:
    """Create a short-lived purpose-scoped JWT (verify, reset, invite). Returns (token, jti)."""
    jti = str(uuid.uuid4())
    expire = datetime.now(timezone.utc) + timedelta(hours=exp_hours)
    payload: dict = {"sub": sub, "purpose": purpose, "jti": jti, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm), jti


def _decode_purpose_token(token: str, expected_purpose: str) -> dict:
    """Decode a purpose-scoped JWT; raise HTTPException on any failure."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError:
        raise HTTPException(400, {"error": "token_expired"})
    except JWTError:
        raise HTTPException(400, {"error": "invalid_token"})

    if payload.get("purpose") != expected_purpose:
        raise HTTPException(400, {"error": "invalid_token"})

    return payload


def _send_email_background(to: str, subject: str, body: str) -> None:
    """Fire-and-forget SMTP send for transactional emails (runs in BackgroundTasks)."""
    if not settings.smtp_host or not settings.smtp_username or not settings.smtp_password:
        logger.warning("SMTP not configured — skipping transactional email to %s", to)
        return
    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_username
        msg["To"] = to
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as s:
            s.starttls()
            s.login(settings.smtp_username, settings.smtp_password)
            s.send_message(msg)
        logger.info("transactional email sent to %s subject=%r", to, subject[:50])
    except Exception as e:
        logger.error("transactional email failed to %s: %s", to, e)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(
    req: RegisterRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """Create a new user scoped to an existing organisation."""
    org_result = await db.execute(select(Organisation).where(Organisation.id == req.org_id))
    if org_result.scalar_one_or_none() is None:
        raise HTTPException(404, {"error": "org_not_found", "message": "Organisation not found"})

    hashed = pwd_context.hash(req.password)
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
        raise HTTPException(409, {"error": "email_already_registered"})

    # Send verification email in background
    verify_token, _ = _make_purpose_token(str(new_user.id), "email_verify", 24)
    verify_url = f"{settings.frontend_url}/verify-email?token={verify_token}"
    background.add_task(
        _send_email_background,
        new_user.email,
        "Verify your PropOps email",
        f"Click to verify your email:\n\n{verify_url}\n\nExpires in 24 hours.",
    )
    new_user.last_verification_sent_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info("register: id=%s email=%s org=%s", new_user.id, new_user.email, new_user.org_id)
    return RegisterResponse(id=new_user.id, email=new_user.email, org_id=new_user.org_id, role=new_user.role)


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate and return a JWT. Primary path uses users table; demo fallback in dev."""
    email = req.email

    # Primary: look up user by email + org_id
    user_result = await db.execute(
        select(User).where(User.email == email, User.org_id == req.org_id)
    )
    db_user = user_result.scalar_one_or_none()

    if db_user is not None:
        try:
            password_ok = pwd_context.verify(req.password, db_user.hashed_password)
        except Exception:
            password_ok = False

        # Always run bcrypt before checking email_verified — avoids timing oracle.
        # Return generic 401 for both wrong password and unverified, log internally.
        if not db_user.email_verified:
            logger.warning("login: unverified email for user id=%s", db_user.id)
            raise HTTPException(401, {"error": "invalid_credentials"})

        if not password_ok:
            logger.warning("login: wrong password for email=%s", email)
            raise HTTPException(401, {"error": "invalid_credentials"})

        token = _make_token(db_user)
        logger.info("login: user id=%s email=%s org=%s", db_user.id, db_user.email, db_user.org_id)
        return LoginResponse(
            access_token=token,
            user={"id": str(db_user.id), "email": db_user.email, "org_id": str(db_user.org_id), "role": db_user.role},
        )

    # Constant-time guard when user not found (prevents email enumeration via timing)
    try:
        pwd_context.verify(req.password, _DUMMY_HASH)
    except Exception:
        pass

    # Demo-credential fallback (non-production only)
    if (
        settings.enable_demo_login
        and settings.environment != "production"
        and settings.demo_email
        and settings.demo_password
        and settings.demo_org_id
    ):
        email_ok = secrets.compare_digest(email, settings.demo_email.strip().lower())
        pass_ok = secrets.compare_digest(req.password, settings.demo_password)
        if email_ok and pass_ok:
            expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
            payload = {
                "sub": _DEMO_SUB,
                "email": settings.demo_email,
                "org_id": str(settings.demo_org_id),
                "role": "founder",
                "jti": str(uuid.uuid4()),
                "exp": expire,
            }
            token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
            logger.info("login: demo session for email=%s", settings.demo_email)
            return LoginResponse(
                access_token=token,
                user={"email": settings.demo_email, "role": "founder", "org_id": str(settings.demo_org_id)},
            )

    raise HTTPException(401, {"error": "invalid_credentials"})


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
                expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
                if jti:
                    await revoke_token_jti(jti, db, expires_at=expires_at)
            except JWTError:
                logger.warning("Logout: could not decode token for revocation")
    return {"status": "logged_out"}


@router.post("/verify-email")
async def verify_email(
    req: EmailVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify email address using signed token from registration email. Idempotent."""
    payload = _decode_purpose_token(req.token, "email_verify")
    user_id = payload.get("sub")

    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(400, {"error": "invalid_token"})

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(400, {"error": "invalid_token"})

    if not user.email_verified:
        user.email_verified = True
        await db.commit()

    return {"status": "verified"}


@router.post("/resend-verification", status_code=202)
async def resend_verification(
    req: ResendVerificationRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Resend verification email. Rate-limited to ~3/hr. Always returns 202 (anti-enumeration)."""
    result = await db.execute(
        select(User).where(User.email == req.email, User.org_id == req.org_id)
    )
    user = result.scalar_one_or_none()

    if user and not user.email_verified:
        now = datetime.now(timezone.utc)
        # ~3/hr = 1 per 20 minutes (1200s)
        if user.last_verification_sent_at:
            since = (now - user.last_verification_sent_at).total_seconds()
            if since < 1200:
                return  # rate limited — still 202

        verify_token, _ = _make_purpose_token(str(user.id), "email_verify", 24)
        verify_url = f"{settings.frontend_url}/verify-email?token={verify_token}"
        background.add_task(
            _send_email_background,
            user.email,
            "Verify your PropOps email",
            f"Click to verify your email:\n\n{verify_url}\n\nExpires in 24 hours.",
        )
        user.last_verification_sent_at = now
        await db.commit()


@router.post("/forgot-password", status_code=202)
async def forgot_password(
    req: ForgotPasswordRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    response: Response = None,
):
    """Send password reset email. Always returns 202 (anti-enumeration). Rate-limited 5/hr."""
    result = await db.execute(
        select(User).where(User.email == req.email, User.org_id == req.org_id)
    )
    user = result.scalar_one_or_none()

    if user and user.email_verified:
        now = datetime.now(timezone.utc)
        # Rate limit: 5/hr = 1 per 720 seconds
        if user.last_reset_sent_at:
            since = (now - user.last_reset_sent_at).total_seconds()
            if since < 720:
                if response:
                    response.status_code = 429
                    response.headers["Retry-After"] = str(int(720 - since))
                return

        reset_token, _ = _make_purpose_token(str(user.id), "password_reset", 1)
        reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"
        background.add_task(
            _send_email_background,
            user.email,
            "Reset your PropOps password",
            f"Click to reset your password:\n\n{reset_url}\n\nExpires in 1 hour. If you didn't request this, ignore this email.",
        )
        user.last_reset_sent_at = now
        await db.commit()


@router.post("/reset-password")
async def reset_password(
    req: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset password using signed single-use token."""
    payload = _decode_purpose_token(req.token, "password_reset")
    jti = payload.get("jti")
    user_id = payload.get("sub")

    if jti and await is_jti_revoked(jti, db):
        raise HTTPException(400, {"error": "token_already_used"})

    try:
        uid = uuid.UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(400, {"error": "invalid_token"})

    result = await db.execute(select(User).where(User.id == uid))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(400, {"error": "invalid_token"})

    # Revoke JTI (single-use enforcement)
    if jti:
        exp = payload.get("exp")
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        await revoke_token_jti(jti, db, expires_at=expires_at)

    user.hashed_password = pwd_context.hash(req.new_password)
    await db.commit()
    return {"status": "password_reset"}


@router.post("/accept-invite", response_model=LoginResponse)
async def accept_invite(
    req: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Accept an org invite: validate token, create user with email_verified=True, return JWT."""
    payload = _decode_purpose_token(req.token, "invite")
    jti = payload.get("jti")
    email = payload.get("sub")
    org_id_str = payload.get("org_id")
    role = payload.get("role", "member")

    if not jti:
        raise HTTPException(400, {"error": "invalid_token"})

    if await is_jti_revoked(jti, db):
        raise HTTPException(400, {"error": "invite_already_used"})

    # Validate invite row still exists and not already accepted
    invite_result = await db.execute(select(Invite).where(Invite.jti == jti))
    invite = invite_result.scalar_one_or_none()
    if not invite:
        raise HTTPException(400, {"error": "invalid_token"})
    if invite.accepted_at:
        raise HTTPException(400, {"error": "invite_already_used"})

    try:
        org_id = uuid.UUID(org_id_str)
    except (ValueError, TypeError):
        raise HTTPException(400, {"error": "invalid_token"})

    hashed = pwd_context.hash(req.password)
    new_user = User(
        org_id=org_id,
        email=email,
        hashed_password=hashed,
        role=role,
        email_verified=True,  # invite acceptance = email already verified
    )
    try:
        db.add(new_user)
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, {"error": "email_already_registered"})

    invite.accepted_at = datetime.now(timezone.utc)
    exp = payload.get("exp")
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
    await revoke_token_jti(jti, db, expires_at=expires_at)
    await db.commit()
    await db.refresh(new_user)

    token = _make_token(new_user)
    logger.info("accept_invite: created user id=%s email=%s org=%s", new_user.id, new_user.email, new_user.org_id)
    return LoginResponse(
        access_token=token,
        user={"id": str(new_user.id), "email": new_user.email, "org_id": str(new_user.org_id), "role": new_user.role},
    )
