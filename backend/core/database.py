"""PostgreSQL async database connection via SQLAlchemy 2.0+.

This module provides:
- Async engine with configurable connection pooling
- Session factory for dependency injection
- Database lifecycle management (init/shutdown)

Never use metadata.create_all() in production — Alembic migrations are canonical.
"""
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from backend.core.config import settings
from backend.models.base import Base
import backend.models.revoked_token  # noqa: F401 — register RevokedToken metadata

logger = logging.getLogger(__name__)

__all__ = ["Base", "engine", "AsyncSessionLocal", "get_db", "init_db"]

# SQL echo routed through dedicated logger — avoids PII leaking to stdout in prod
_db_logger = logging.getLogger("sqlalchemy.engine")
if settings.environment == "development":
    _db_logger.setLevel(logging.DEBUG)

# Create async engine with connection pooling
# Pool settings are tunable via environment variables (see config.py)
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    echo_pool=False,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args={
        "server_settings": {"application_name": "propops"},
        "timeout": settings.database_pool_timeout,
    },
)

# Session factory for FastAPI dependency injection
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields async DB session.

    Automatically commits on success, rolls back on exception.
    
    WARNING: Do NOT call init_db() from here. Use Alembic migrations as canonical.
    
    Usage:
        async def my_route(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    
    Yields:
        AsyncSession: Database session with automatic rollback on error.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            if session.new or session.dirty or session.deleted:
                await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Verify database connectivity at startup.

    Schema changes are applied exclusively via Alembic migrations —
    never call metadata.create_all() here.
    """
    from sqlalchemy import text

    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
    logger.info("Database connectivity verified (Alembic owns schema migrations)")

