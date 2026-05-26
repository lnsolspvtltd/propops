"""Pytest configuration and shared fixtures."""
import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.database import Base, get_db
from backend.models.incident import Organization, Incident, AIDraft, Unit, Property


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_db():
    """Create an in-memory SQLite async database for tests."""
    # Use SQLite for testing (simpler than PostgreSQL)
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"timeout": 30},
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    AsyncSessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with AsyncSessionLocal() as session:
        yield session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def client(test_db):
    """FastAPI test client with mocked database."""
    async def override_get_db():
        yield test_db
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def test_org(test_db) -> Organization:
    """Create a test organization."""
    org = Organization(
        id="00000000-0000-0000-0000-000000000001",
        name="Test Property Management",
        email_domain="pm.test",
        plan="beta",
    )
    test_db.add(org)
    await test_db.commit()
    await test_db.refresh(org)
    return org


@pytest.fixture
async def test_property(test_db, test_org) -> Property:
    """Create a test property."""
    prop = Property(
        id="10000000-0000-0000-0000-000000000001",
        org_id=test_org.id,
        name="123 Main Street",
        address="123 Main Street, Toronto, ON M1M 1M1",
        city="Toronto",
    )
    test_db.add(prop)
    await test_db.commit()
    await test_db.refresh(prop)
    return prop


@pytest.fixture
async def test_unit(test_db, test_property) -> Unit:
    """Create a test unit."""
    unit = Unit(
        id="20000000-0000-0000-0000-000000000001",
        property_id=test_property.id,
        unit_number="4B",
        tenant_name="Jane Doe",
        tenant_email="jane@example.com",
    )
    test_db.add(unit)
    await test_db.commit()
    await test_db.refresh(unit)
    return unit


@pytest.fixture
async def test_incident(test_db, test_org) -> Incident:
    """Create a test incident."""
    incident = Incident(
        id="30000000-0000-0000-0000-000000000001",
        org_id=test_org.id,
        title="Tenant reports broken sink",
        category="maintenance",
        urgency="MEDIUM",
        status="OPEN",
        ai_summary="Tenant Jane Doe reports that the sink in Unit 4B is leaking water.",
        ai_confidence=0.92,
        source_channel="email",
        source_address="jane@example.com",
        raw_message="Hi, my sink is broken and water is leaking everywhere. Please help!",
    )
    test_db.add(incident)
    await test_db.commit()
    await test_db.refresh(incident)
    return incident


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic client for draft generation tests."""
    with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client
