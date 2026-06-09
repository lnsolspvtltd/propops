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
from jose import jwt, JWTError, ExpiredSignatureError
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
    await db.commit()
    # Add to cache only after successful DB commit — prevents false positives on commit failure
    _revoked_jti_cache.add(jti)


async def purge_expired_revocations(db: AsyncSession) -> None:
    """Remove expired entries from the blocklist (best-effort housekeeping)."""
    now = datetime.now(timezone.utc)
    await db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
    await db.commit()


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Extract and validate current user from JWT token in Authorization header.

    Expected header format: Authorization: Bearer <token>

    Args:
        authorization: Authorization header value (injected by FastAPI)

    Returns:
        dict with user info (id, email, etc.)

    Raises:
        HTTPException 401: Missing, invalid, or expired token
    """
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
        # Verify and decode JWT
        payload = jwt.decode(
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

        # Accept both "sub" (new tokens) and "user_id" (legacy tokens) for backward compat
        user_id: str = payload.get("sub") or payload.get("user_id")
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
            "email": payload.get("email"),
            "role": payload.get("role", "member"),
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

    except JWTError as e:
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
        raise HTTPException(status_code=401, detail={"error": "internal_error"})


def assert_org(user: Dict[str, Any], requested_org_id) -> None:
    """Raise 403 if the JWT org_id does not match requested_org_id.

    Call this inside any route that scopes data to a single organisation to
    prevent cross-tenant data leakage.

    Args:
        user: Dict returned by get_current_user dependency.
        requested_org_id: The org UUID from the URL path or request body.

    Raises:
        HTTPException 403: when org_id in the token does not match or is absent.
    """
    jwt_org_id = user.get("org_id")
    if not jwt_org_id:
        logger.warning("assert_org: token has no org_id claim")
        raise HTTPException(
            status_code=403,
            detail={"error": "org_mismatch", "message": "No org in token"},
        )
    if str(jwt_org_id) != str(requested_org_id):
        logger.warning(
            "assert_org: token org_id=%s does not match requested_org_id=%s",
            jwt_org_id,
            requested_org_id,
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "org_mismatch"},
        )
