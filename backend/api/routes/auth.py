"""Authentication routes — login + token management."""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from jose import jwt
from pydantic import BaseModel

from backend.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

# Demo credentials — gate on development mode only
DEMO_EMAIL = "demo@propops.app"
DEMO_PASSWORD = "propops2026"


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest) -> LoginResponse:
    """Authenticate and return JWT.

    Demo mode: accepts demo@propops.app / propops2026
    In production, swap this for a real user table lookup.
    """
    email = req.email.strip().lower()
    # Demo auth — accept demo creds or any email with demo password in development
    is_valid = (
        (email == DEMO_EMAIL and req.password == DEMO_PASSWORD) or
        (settings.environment == "development" and req.password == DEMO_PASSWORD)
    )
    
    # Security check: prevent demo credentials in production
    if settings.environment == "production" and req.password == DEMO_PASSWORD:
        raise RuntimeError("Demo credentials not allowed in production")
    
    if not is_valid:
        raise HTTPException(status_code=401, detail={"error": "Invalid credentials"})

    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": email, "exp": expire, "name": email.split("@")[0].title()}
    token = jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)

    logger.info("Login: %s", email)
    return LoginResponse(
        access_token=token,
        user={"email": email, "name": email.split("@")[0].title()},
    )


@router.post("/logout")
async def logout() -> dict:
    """Client should discard the token. Server is stateless."""
    return {"status": "logged_out"}