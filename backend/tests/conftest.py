"""Pytest configuration and shared fixtures."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from backend.core.database import Base
from backend.models.incident import (
    Organization, Property, Unit, Incident, AIDraft, CommunicationLog
)


@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session():
    """Create in-memory SQLite async session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()

    await engine.dispose()


@pytest.fixture
async def test_org(db_session: AsyncSession):
    """Create a test organization."""
    org = Organization(
        id=uuid.uuid4(),
        name="Test Property Management",
        email_domain="test-pm.com",
        plan="beta",
        unit_count=5,
    )
    db_session.add(org)
    await db_session.flush()
    return org


@pytest.fixture
async def test_property(db_session: AsyncSession, test_org: Organization):
    """Create a test property."""
    prop = Property(
        id=uuid.uuid4(),
        org_id=test_org.id,
        name="123 Main St",
        address="123 Main Street",
        city="Toronto",
        unit_count=3,
    )
    db_session.add(prop)
    await db_session.flush()
    return prop


@pytest.fixture
async def test_unit(db_session: AsyncSession, test_property: Property):
    """Create a test unit."""
    unit = Unit(
        id=uuid.uuid4(),
        property_id=test_property.id,
        unit_number="201",
        tenant_name="John Smith",
        tenant_email="john@example.com",
        tenant_phone="+1-416-555-0123",
    )
    db_session.add(unit)
    await db_session.flush()
    return unit


@pytest.fixture
async def test_incident(db_session: AsyncSession, test_org: Organization, test_property: Property, test_unit: Unit):
    """Create a test incident."""
    incident = Incident(
        id=uuid.uuid4(),
        org_id=test_org.id,
        property_id=test_property.id,
        unit_id=test_unit.id,
        thread_id=uuid.uuid4(),
        title="Broken pipe in unit 201",
        category="maintenance",
        urgency="HIGH",
        status="OPEN",
        ai_summary="Water leak from bathroom pipe needs immediate attention",
        ai_confidence=0.95,
        source_channel="email",
        source_address="john@example.com",
        raw_message="Water is leaking from the pipe under the sink",
    )
    db_session.add(incident)
    await db_session.flush()
    return incident


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client for testing."""
    return MagicMock()


@pytest.fixture
def mock_triage_result():
    """Mock triage result."""
    from backend.ai.triage_agent import TriageResult
    return TriageResult(
        category="maintenance",
        urgency="HIGH",
        title="Broken pipe in unit 201",
        summary="Water leak from bathroom pipe needs immediate attention",
        sentiment="frustrated",
        unit_mentioned="201",
        requires_vendor=True,
        confidence=0.95,
        tags=["plumbing", "emergency", "water_damage"],
        model_used="claude-haiku-4-5",
        success=True,
    )


@pytest.fixture
def mock_draft_result():
    """Mock draft result."""
    from backend.ai.draft_agent import DraftResult
    return DraftResult(
        subject="Re: URGENT: Broken pipe in unit 201",
        body="Thank you for reporting this issue. We take this very seriously and have scheduled an emergency plumber to visit your unit within 2 hours. We will call you to confirm the appointment time.",
        draft_type="tenant_reply",
        model_used="claude-sonnet-4-5-20251001",
        success=True,
    )
---