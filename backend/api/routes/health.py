"""Health check endpoint."""
import logging
from fastapi import APIRouter
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok", "service": "propops-api", "timestamp": datetime.now(timezone.utc).isoformat()}
