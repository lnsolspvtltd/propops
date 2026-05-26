"""Authentication and authorization utilities."""
import logging
from typing import Optional
from fastapi import Depends, HTTPException, Header
import jwt
from backend.core.config import settings

logger = logging.getLogger(__name__)


async def get_current_user(
    authorization: Optional[str] = Header(None)
) -> str:
    """Extract and validate JWT token from Authorization header.
    
    # SECURITY-REVIEW: This is a minimal JWT validator.
    # Production should validate against your issuer, check exp claim,
    # and verify user exists in database.
    
    Args:
        authorization: Bearer token from Authorization header
        
    Returns:
        Authenticated user identifier (subject claim)
        
    Raises:
        HTTPException: 401 if token missing or invalid
    """
    if not authorization:
        logger.warning("Missing authorization header")
        raise HTTPException(status_code=401, detail="Missing authorization header")
    
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            logger.warning(f"Invalid auth scheme: {scheme}")
            raise HTTPException(status_code=401, detail="Invalid authorization scheme")
        
        # Decode JWT without verification (for MVP)
        # TODO: Add signature verification with settings.jwt_secret_key
        payload = jwt.decode(token, options={"verify_signature": False})
        user_id = payload.get("sub")
        
        if not user_id:
            logger.warning("JWT missing 'sub' claim")
            raise HTTPException(status_code=401, detail="Invalid token: missing subject")
        
        logger.debug(f"Authenticated user: {user_id}")
        return user_id
    
    except ValueError as e:
        logger.warning(f"Malformed authorization header: {e}")
        raise HTTPException(status_code=401, detail="Malformed authorization header")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Error in get_current_user: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail="Authentication failed")
---