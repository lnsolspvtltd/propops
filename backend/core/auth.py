"""Authentication and authorization module.

Provides dependency injection for getting current user from request.
Uses JWT tokens in Authorization header.

SECURITY-REVIEW: This module handles user authentication.
- Tokens are validated server-side
- User info is extracted from verified token
- Invalid/expired tokens return 401 Unauthorized
"""
import logging
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, Header
from jwt import decode, DecodeError, ExpiredSignatureError
import jwt

from backend.core.config import settings

logger = logging.getLogger(__name__)


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
        HTTPException 401: Missing or invalid token
        HTTPException 403: Expired or tampered token
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
        logger.warning(f"get_current_user: Invalid Authorization header format")
        raise HTTPException(
            status_code=401,
            detail={
                "error": "invalid_authorization_format",
                "message": "Use: Authorization: Bearer <token>"
            }
        )
    
    token = parts[1]
    
    try:
        # Verify and decode JWT
        payload = decode(
            token,
            settings.secret_key,
            algorithms=["HS256"]
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
            "role": payload.get("role", "user"),
            "org_id": payload.get("org_id"),
        }
    
    except ExpiredSignatureError:
        logger.warning("get_current_user: Token expired")
        raise HTTPException(
            status_code=403,
            detail={
                "error": "token_expired",
                "message": "Token has expired"
            }
        )
    
    except DecodeError as e:
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
        raise HTTPException(
            status_code=500,
            detail="Internal error validating token"
        )


def assert_org(user: Dict[str, Any], requested_org_id) -> None:
    """Raise 403 if the JWT org_id does not match requested_org_id.

    Call this inside any route that scopes data to a single organisation to
    prevent cross-tenant data leakage.

    Args:
        user: Dict returned by get_current_user dependency.
        requested_org_id: The org UUID from the URL path or request body.

    Raises:
        HTTPException 403: when org_id in the token does not match.
    """
    if str(user.get("org_id", "")) != str(requested_org_id):
        logger.warning(
            "assert_org: token org_id=%s does not match requested_org_id=%s",
            user.get("org_id"),
            requested_org_id,
        )
        raise HTTPException(
            status_code=403,
            detail={"error": "org_mismatch"},
        )