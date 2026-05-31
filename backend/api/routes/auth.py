"""Authentication routes — register, login, and token management.

Real user auth backed by the `users` table.  bcrypt password hashing via
passlib.  JWT tokens include sub, email, org_id, role, and jti claims.

Demo-credential fallback is gated by settings.enable_demo_login and is
disabled automatically in production regardless of that flag.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.models.organisation import Organisation
from backend.models.user import User

try:
    from jose import jwt
except ImportError:
    import jwt  # type: ignore[no-redef]

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

# bcrypt context — auto-handles future algorithm migrations
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Payload for POST /register."""

    email: str
    password: str
    org_id: uuid.UUID
    role: str = "member"

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
    email: str
    password: str


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
    - exp   — TOKEN_EXPIRE_HOURS from now
    """
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "org_id": str(user.org_id),
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


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
            detail={"error": "org_not_found", "org_id": str(req.org_id)},
        )

    # 2. Check for duplicate email within this org
    dup_result = await db.execute(
        select(User).where(User.email == req.email, User.org_id == req.org_id)
    )
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "email_already_registered"},
        )

    # 3. Hash password — the plaintext is discarded immediately
    hashed = pwd_context.hash(req.password)

    # 4. Persist
    new_user = User(
        org_id=req.org_id,
        email=req.email,
        hashed_password=hashed,
        role=req.role,
        email_verified=False,
    )
    db.add(new_user)
    await db.flush()  # populate new_user.id before commit
    await db.commit()
    await db.refresh(new_user)

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
    environment is not production, the legacy demo credentials are accepted as
    a secondary path so existing development workflows keep working.
    """
    email = req.email.strip().lower()

    # ------------------------------------------------------------------
    # Real user table lookup (primary path)
    # ------------------------------------------------------------------
    user_result = await db.execute(select(User).where(User.email == email))
    db_user = user_result.scalar_one_or_none()

    if db_user is not None:
        # Verify bcrypt hash — constant-time comparison handled by passlib
        if not pwd_context.verify(req.password, db_user.hashed_password):
            logger.warning("login: wrong password for email=%s", email)
            raise HTTPException(status_code=401, detail={"error": "invalid_credentials"})

        if not db_user.email_verified:
            logger.warning("login: unverified email for user id=%s", db_user.id)
            raise HTTPException(status_code=403, detail={"error": "email_not_verified"})

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

    # ------------------------------------------------------------------
    # Demo-credential fallback (non-production only)
    # ------------------------------------------------------------------
    if settings.enable_demo_login and settings.environment != "production":
        if not settings.demo_email or not settings.demo_password:
            logger.error("login: demo credentials not configured")
            raise HTTPException(status_code=500, detail={"error": "server_configuration_error"})

        is_demo = (email == settings.demo_email and req.password == settings.demo_password) or (
            settings.environment == "development" and req.password == settings.demo_password
        )
        if is_demo:
            expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
            payload = {
                "sub": email,
                "email": email,
                "org_id": None,
                "role": "admin",
                "jti": str(uuid.uuid4()),
                "exp": expire,
            }
            token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)
            logger.info("login: demo session for email=%s", email)
            return LoginResponse(
                access_token=token,
                user={"email": email, "name": email.split("@")[0].title(), "role": "admin"},
            )

    # No match in users table and demo fallback didn't apply
    raise HTTPException(status_code=401, detail={"error": "invalid_credentials"})


@router.post("/logout")
async def logout() -> dict:
    """Client must discard the token. Server is stateless for now."""
    return {"status": "logged_out"}
