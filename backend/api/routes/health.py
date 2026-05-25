"""Health check endpoint."""
from fastapi import APIRouter
from datetime import datetime, timezone
from backend.core.config import get_settings

router = APIRouter()

@router.get("/health")
async def health():
    """Health check endpoint with version info for observability."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": "propops-api",
        "version": settings.version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
---