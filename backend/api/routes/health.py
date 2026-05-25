"""Health check endpoint."""
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint for load balancer.
    
    Returns 200 OK if:
    - Service is running
    - Database is reachable and responding
    
    Returns 503 Service Unavailable if database is down.
    
    Returns:
        JSON with status, service name, timestamp, and dependency status
        
    Raises:
        HTTPException: If database is unreachable (503)
    """
    try:
        # Lightweight database ping to verify connectivity
        await db.execute(text("SELECT 1"))
        
        return {
            "status": "ok",
            "service": "propops-api",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dependencies": {
                "database": "healthy"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: database unreachable. {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unavailable",
                "service": "propops-api",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dependencies": {
                    "database": "unhealthy"
                },
                "error": "Database connection failed"
            }
        )
---