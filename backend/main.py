from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker

from backend.api.routes.tenants import router as tenants_router
from backend.api.routes.units import router as units_router

app = FastAPI()

# Database setup
DATABASE_URL = "sqlite:///./propops.db"
engine = create_async_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)