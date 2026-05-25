"""PropOps Backend — FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import settings
from backend.core.database import init_db
from backend.services.inbox_poller import start_inbox_poller, stop_inbox_poller
from backend.api.routes import inbox, incidents, approvals, health

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.
    
    Startup:
      - Initialize database
      - Start inbox poller background task (graceful degradation if fails)
      
    Shutdown:
      - Stop inbox poller gracefully
    """
    logger.info("PropOps starting up...")
    
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)
        raise  # Block startup if DB init fails
    
    try:
        await start_inbox_poller()
        logger.info("Inbox poller started")
    except Exception as e:
        # Log but do NOT block startup — graceful degradation
        logger.warning(
            f"Failed to start inbox poller: {e}. "
            f"Application will continue but automated email ingestion is disabled.",
            exc_info=True,
        )
    
    yield
    
    logger.info("PropOps shutting down...")
    try:
        await stop_inbox_poller()
    except Exception as e:
        logger.warning(f"Error stopping inbox poller: {e}", exc_info=True)


app = FastAPI(
    title="PropOps API",
    description="AI Operational Middleware for Property Managers",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(inbox.router, prefix="/api/v1/inbox", tags=["inbox"])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])
app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {"service": "PropOps API", "version": "0.1.0", "status": "running"}
