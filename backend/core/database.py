"""PostgreSQL async database connection via SQLAlchemy 2.0+."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from backend.core.config import settings
from backend.models.incident import Base

logger = logging.getLogger(__name__)

# Create async engine with connection pooling optimized for FastAPI
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",  # SQL logging only in dev
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before use
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db():
    """Initialize database — create all tables from models.
    
    Called on application startup via lifespan context manager.
    Safe to run multiple times (idempotent with CREATE TABLE IF NOT EXISTS).
    """
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialization complete")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise


async def get_db():
    """FastAPI dependency — yields async DB session.
    
    Automatically commits on success, rolls back on exception.
    Usage:
        async def my_route(db: AsyncSession = Depends(get_db)):
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}", exc_info=True)
            raise


async def close_db():
    """Close all database connections (called on app shutdown)."""
    await engine.dispose()
```

---