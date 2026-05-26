from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from .models import Base

DATABASE_URL = "postgresql+asyncpg://user:password@localhost/propops"

engine = create_async_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def get_db():
    async with SessionLocal() as db:
        yield db
```

---

### SECTION 14 — TESTS WRITTEN