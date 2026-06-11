"""PropOps Backend — FastAPI application entry point."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import approvals, health, inbox, incidents
from backend.api.routes import dashboard, tenants, units, vendors, onboarding
from backend.api.routes import incidents_assign, auth, demo, onboarding_settings, invites
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
    """Application lifespan — startup/shutdown hooks."""
    logger.info("PropOps starting up...")
    try:
        validate_startup_settings()
    except SystemExit:
        raise

    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.critical(f"Database init failed: {e}", exc_info=True)
        raise

    try:
        await start_inbox_poller()
        logger.info("Inbox poller started")
    except Exception as e:
        logger.warning(f"Inbox poller failed to start: {e}. Continuing without it.", exc_info=True)

    yield

    logger.info("PropOps shutting down...")
    try:
        await stop_inbox_poller()
    except Exception as e:
        logger.warning(f"Error stopping inbox poller: {e}", exc_info=True)


settings = get_settings()

app = FastAPI(
    title="PropOps API",
    description="AI Operational Middleware for Property Managers",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Phase 1 routes
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(inbox.router, prefix="/api/v1/inbox", tags=["inbox"])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"])
app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["approvals"])
app.include_router(auth.router)
if settings.environment == "development":
    app.include_router(demo.router)

# Phase 2 routes
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(tenants.router, prefix="/api/v1")
app.include_router(units.router, prefix="/api/v1")
app.include_router(vendors.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(onboarding_settings.router, prefix="/api/v1")
app.include_router(incidents_assign.router, prefix="/api/v1")

# Phase 4 routes
app.include_router(invites.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"service": "PropOps API", "version": "0.2.0", "status": "running"}
