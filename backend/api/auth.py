"""Authentication and JWT token handling."""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthCredentials
from pydantic import BaseModel
from backend.core.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """JWT token payload structure."""
    user_id: str
    email: str
    org_id: Optional[str] = None
    role: str  # "admin" | "manager" | "member"
    exp: datetime


class User(BaseModel):
    """Authenticated user identity."""
    user_id: str
    email: str
    org_id: Optional[str] = None
    role: str


def create_access_token(
    user_id: str,
    email: str,
    org_id: Optional[str] = None,
    role: str = "member",
) -> str:
    """
    Create a JWT access token.

    Args:
        user_id: Unique user identifier
        email: User email address
        org_id: Organisation UUID string (scopes token to a tenant)
        role: User role (admin, manager, member)

    Returns:
        Encoded JWT token string
    """
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "user_id": user_id,
        "email": email,
        "org_id": org_id,
        "role": role,
        "jti": str(uuid.uuid4()),
        "exp": expires,
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    logger.debug(f"Created access token for user_id={user_id}")
    return token


def verify_token(token: str) -> TokenPayload:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        TokenPayload with validated claims
    
    Raises:
        JWTError: If token is invalid, expired, or tampered
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        return TokenPayload(
            user_id=payload["user_id"],
            email=payload["email"],
            org_id=payload.get("org_id"),
            role=payload.get("role", "member"),
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    except JWTError as e:
        logger.warning(f"Invalid token: {e}")
        raise JWTError(f"Invalid or expired token: {e}")


async def get_current_user(credentials: Optional[HTTPAuthCredentials] = Depends(security)) -> User:
    """
    Dependency to extract and validate current user from Authorization header.
    
    Args:
        credentials: HTTP Bearer token from Authorization header
    
    Returns:
        User object with authenticated identity
    
    Raises:
        HTTPException 401: If no token or token is invalid
    """
    if not credentials:
        logger.warning("Request without Authorization header")
        raise HTTPException(status_code=401, detail="Missing authorization token")
    
    try:
        token_payload = verify_token(credentials.credentials)
    except JWTError as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return User(
        user_id=token_payload.user_id,
        email=token_payload.email,
        org_id=token_payload.org_id,
        role=token_payload.role,
    )


def require_role(required_role: str):
    """
    Dependency factory to require a specific role.
    
    Args:
        required_role: Role required to access endpoint (e.g. "admin")
    
    Returns:
        Async dependency function
    """
    async def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role != required_role and user.role != "admin":
            logger.warning(f"User {user.email} with role {user.role} denied access to {required_role} endpoint")
            raise HTTPException(status_code=403, detail=f"Requires {required_role} role")
        return user
    
    return check_role

