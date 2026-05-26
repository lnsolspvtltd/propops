"""Health check endpoint."""
from functools import lru_cache
from fastapi import APIRouter
from datetime import datetime, timezone
from backend.core.config import get_settings

router = APIRouter()


@lru_cache(maxsize=1)
def _get_settings_cached():
    """Cache settings to avoid repeated file I/O on every health check."""
    return get_settings()


@router.get("/health")
async def health():
    """Health check endpoint with version info for observability.
    
    Returns:
        JSON with service status, version, environment, and timestamp
    """
    settings = _get_settings_cached()
    return {
        "status": "ok",
        "service": "propops-api",
        "version": settings.version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
---