"""Authentication and authorization module.

Provides dependency injection for getting current user from request.
Uses JWT tokens in Authorization header.

SECURITY-REVIEW: This module handles user authentication.
- Tokens are validated server-side
- User info is extracted from verified token
- Invalid/expired tokens return 401 Unauthorized
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, Header
from jose import jwt, JWTError, ExpiredSignatureError

from backend.core.config import settings

logger = logging.getLogger(__name__)

_REVOKED_JTI_PATH = Path(os.environ.get("REVOKED_JTI_FILE", ".revoked_jtis.json"))


def _load_revoked_jtis() -> set[str]:
    """Load revoked token JTIs from disk (survives process restarts)."""
    if not _REVOKED_JTI_PATH.exists():
        return set()
    try:
        return set(json.loads(_REVOKED_JTI_PATH.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not load revoked JTIs: %s", e)
        return set()


def _persist_revoked_jtis(revoked: set[str]) -> None:
    """Persist revoked JTIs to disk."""
    try:
        _REVOKED_JTI_PATH.write_text(json.dumps(sorted(revoked)), encoding="utf-8")
    except OSError as e:
        logger.error("Could not persist revoked JTIs: %s", e)


_revoked_jtis: set[str] = _load_revoked_jtis()


def revoke_token_jti(jti: str) -> None:
    """Mark a token jti as revoked (logout / stolen token)."""
    _revoked_jtis.add(jti)
    _persist_revoked_jtis(_revoked_jtis)


async def get_current_user(
    authorization: Optional[str] = Header(None),
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
                "message": "Authorization header required"
            }
        )

    # Extract token from "Bearer <token>"
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.warning("get_current_user: Invalid Authorization header format")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_authorization_format",
                "message": "Use: Authorization: Bearer <token>"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    try:
        # Verify and decode JWT
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        jti = payload.get("jti")
        if jti and jti in _revoked_jtis:
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
                    "message": "Token missing user ID"
                }
            )

        logger.debug(f"get_current_user: Valid token for user_id={user_id}")
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
                "message": "Token has expired"
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    except JWTError as e:
        logger.warning(f"get_current_user: Token decode error: {e}")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_token",
                "message": "Token is invalid or tampered"
            }
        )

    except Exception as e:
        logger.error(f"get_current_user: Unexpected error: {e}", exc_info=True)
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
