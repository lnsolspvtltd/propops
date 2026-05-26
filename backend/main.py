"""PropOps Backend — FastAPI application entry point."""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import approvals, health, inbox, incidents
from backend.core.config import get_settings, validate_startup_settings
from backend.core.database import init_db
from backend.services.inbox_poller import start_inbox_poller, stop_inbox_poller

logging.basicConfig(
    level=get_settings().log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Startup:
      - Validate critical settings for current environment
      - Initialize database
      - Start inbox poller background task (graceful degradation if fails)

    Shutdown:
      - Stop inbox poller gracefully
    """
    logger.info("PropOps starting up...")

    # Validate settings early
    try:
        validate_startup_settings()
    except SystemExit:
        raise  # Re-raise sys.exit to block startup

    # Initialize database — critical for operation
    try:
        await init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.critical(f"Database initialization failed: {e}", exc_info=True)
        raise  # Block startup if DB init fails

    # Start inbox poller — non-critical, log failure but continue
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
        logger.info("Inbox poller stopped gracefully")
    except Exception as e:
        logger.warning(f"Error stopping inbox poller: {e}", exc_info=True)


settings = get_settings()

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
    """Root endpoint — returns service status."""
    return {"service": "PropOps API", "version": "0.1.0", "status": "running"}
---