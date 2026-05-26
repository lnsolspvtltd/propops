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

logger = logging.getLogger(__name__)

# Create async engine with connection pooling
# Pool settings are tunable via environment variables (see config.py)
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",  # SQL logging only in dev; disable for prod
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
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Database session error: %s", e, exc_info=True)
            raise


async def close_db() -> None:
    """Close all database connections.
    
    Called on application shutdown via lifespan context manager.
    Ensures all connection pool connections are properly disposed.
    """
    await engine.dispose()
    logger.info("Database connections closed")
---