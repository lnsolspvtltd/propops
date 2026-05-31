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

    Demo mode: accepts demo credentials only in development/test environments
    In production, swap this for a real user table lookup.
    """
    # Validate required settings exist
    if not settings.demo_email or not settings.demo_password:
        logger.error("Missing required demo credentials in settings")
        raise HTTPException(
            status_code=500,
            detail={"error": "Server configuration error"}
        )
    
    email = req.email.strip().lower()
    
    # Security check: prevent demo credentials in production
    if settings.environment == "production" and req.password == settings.demo_password:
        raise HTTPException(
            status_code=403,
            detail={"error": "Demo credentials not allowed in production"}
        )
    
    # Demo auth — accept demo creds or any email with demo password in development
    is_valid = (
        (email == settings.demo_email and req.password == settings.demo_password) or
        (settings.environment == "development" and req.password == settings.demo_password)
    )
    
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