"""Authentication and authorization module.

Provides dependency injection for getting current user from request.
Uses JWT tokens in Authorization header.

SECURITY-REVIEW: This module handles user authentication.
- Tokens are validated server-side
- User info is extracted from verified token
- Invalid/expired tokens return 401 Unauthorized
- Revoked JTIs are checked against the DB blocklist (multi-worker safe)
- Hot-path positive cache avoids a DB round-trip on repeat revoked checks
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, Header
from jwt import decode, DecodeError, ExpiredSignatureError
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.database import get_db
from backend.models.revoked_token import RevokedToken

logger = logging.getLogger(__name__)

# Process-local positive cache: revoked JTIs only (cleared on restart).
# Multi-worker: each worker has its own cache; DB remains source of truth.
_revoked_jti_cache: set[str] = set()


async def is_jti_revoked(jti: str, db: AsyncSession) -> bool:
    """Return True if jti is in the DB revocation blocklist."""
    if jti in _revoked_jti_cache:
        return True
    result = await db.execute(select(RevokedToken.jti).where(RevokedToken.jti == jti))
    revoked = result.scalar_one_or_none() is not None
    if revoked:
        _revoked_jti_cache.add(jti)
    return revoked


async def revoke_token_jti(
    jti: str,
    db: AsyncSession,
    expires_at: datetime | None = None,
) -> None:
    """Mark a token jti as revoked (logout / stolen token). Persists to DB."""
    existing = await db.execute(select(RevokedToken).where(RevokedToken.jti == jti))
    if existing.scalar_one_or_none():
        _revoked_jti_cache.add(jti)
        return
    db.add(RevokedToken(jti=jti, expires_at=expires_at))
    _revoked_jti_cache.add(jti)
    await db.commit()


async def purge_expired_revocations(db: AsyncSession) -> None:
    """Remove expired entries from the blocklist (best-effort housekeeping)."""
    now = datetime.now(timezone.utc)
    await db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
    await db.commit()


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Extract and validate current user from JWT token in Authorization header."""
    if not authorization:
        logger.warning("get_current_user: Missing Authorization header")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_authorization",
                "message": "Authorization header required",
            },
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("get_current_user: Invalid Authorization header format")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_authorization_format",
                "message": "Use: Authorization: Bearer <token>",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        payload = decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        jti = payload.get("jti")
        if jti and await is_jti_revoked(jti, db):
            logger.warning("get_current_user: Token revoked (jti blocklist)")
            raise HTTPException(
                status_code=401,
                detail={"error": "token_revoked", "message": "Token has been revoked"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id: str = payload.get("sub")
        if not user_id:
            logger.warning("get_current_user: Token missing 'sub' claim")
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "invalid_token",
                    "message": "Token missing user ID",
                },
            )

        logger.debug("get_current_user: Valid token for user_id=%s", user_id)
        return {
            "id": user_id,
            "email": payload.get("email") or user_id,
            "role": payload.get("role", "user"),
            "org_id": payload.get("org_id"),
        }

    except ExpiredSignatureError:
        logger.warning("get_current_user: Token expired")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "token_expired",
                "message": "Token has expired",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except DecodeError as e:
        logger.warning("get_current_user: Token decode error: %s", e)
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_token",
                "message": "Token is invalid or tampered",
            },
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error("get_current_user: Unexpected error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal error validating token",
        )
