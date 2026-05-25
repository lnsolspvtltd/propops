"""Shared pytest fixtures for all backend tests."""
import pytest
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.core.database import Base, get_db
from backend.models.incident import Organization, Property, Unit, Incident, AIDraft, CommunicationLog


# ── Database Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
async def test_db():
    """In-memory async SQLite database for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def get_test_db():
        async with async_session() as session:
            yield session
    
    yield async_session
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def client(test_db):
    """FastAPI test client with mocked database."""
    async def override_get_db():
        async with test_db() as session:
            yield session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    
    app.dependency_overrides.clear()


# ── Model Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
async def org(test_db):
    """Create a test organization."""
    async with test_db() as db:
        org = Organization(
            id=uuid.uuid4(),
            name="Test Property Management",
            email_domain="test-pm.com",
            plan="beta",
            unit_count=10,
        )
        db.add(org)
        await db.commit()
        await db.refresh(org)
        return org


@pytest.fixture
async def property_obj(test_db, org):
    """Create a test property."""
    async with test_db() as db:
        prop = Property(
            id=uuid.uuid4(),
            org_id=org.id,
            name="123 Main Street",
            address="123 Main St",
            city="Toronto",
            unit_count=5,
        )
        db.add(prop)
        await db.commit()
        await db.refresh(prop)
        return prop


@pytest.fixture
async def unit(test_db, property_obj):
    """Create a test unit."""
    async with test_db() as db:
        u = Unit(
            id=uuid.uuid4(),
            property_id=property_obj.id,
            unit_number="402",
            tenant_name="John Doe",
            tenant_email="john@example.com",
            tenant_phone="+14165551234",
        )
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u


@pytest.fixture
async def incident(test_db, org, property_obj, unit):
    """Create a test incident."""
    async with test_db() as db:
        inc = Incident(
            id=uuid.uuid4(),
            org_id=org.id,
            property_id=property_obj.id,
            unit_id=unit.id,
            thread_id=uuid.uuid4(),
            title="Broken pipe in kitchen",
            category="maintenance",
            urgency="HIGH",
            status="OPEN",
            ai_summary="Tenant reports water leak in kitchen sink",
            ai_confidence=0.95,
            source_channel="email",
            source_address="john@example.com",
            raw_message="Water is dripping from under the sink",
        )
        db.add(inc)
        await db.commit()
        await db.refresh(inc)
        return inc


@pytest.fixture
async def draft(test_db, incident):
    """Create a test draft."""
    async with test_db() as db:
        d = AIDraft(
            id=uuid.uuid4(),
            incident_id=incident.id,
            draft_type="tenant_reply",
            recipient_email="john@example.com",
            subject="Re: Broken pipe in kitchen",
            body="Thank you for reporting this issue. We will have a plumber out within 24 hours.",
            ai_model="claude-sonnet-4-5-20251001",
            confidence=0.92,
            status="pending",
        )
        db.add(d)
        await db.commit()
        await db.refresh(d)
        return d


# ── Mock Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client."""
    client = AsyncMock()
    return client


@pytest.fixture
def mock_triage_response():
    """Mock successful triage response."""
    return {
        "category": "maintenance",
        "urgency": "HIGH",
        "title": "Broken pipe in kitchen",
        "summary": "Tenant reports water leak under kitchen sink. Requires immediate plumbing repair.",
        "sentiment": "urgent",
        "unit_mentioned": "402",
        "requires_vendor": True,
        "confidence": 0.95,
        "tags": ["plumbing", "water", "urgent"],
    }


@pytest.fixture
def mock_draft_response():
    """Mock successful draft response."""
    return {
        "subject": "URGENT: We're addressing your plumbing issue",
        "body": "Thank you for reporting this immediately. We understand the urgency of water damage. A licensed plumber will be at your unit within 2 hours. Please leave your door unlocked or ensure someone is home.",
        "draft_type": "tenant_reply",
        "model_used": "claude-sonnet-4-5-20251001",
        "success": True,
    }


@pytest.fixture
def mock_settings():
    """Mock application settings."""
    settings = MagicMock()
    settings.anthropic_api_key = "test-key-12345"
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.imap_host = "imap.gmail.com"
    settings.imap_port = 993
    settings.imap_username = "test@gmail.com"
    settings.imap_password = "test-password"
    settings.imap_poll_interval_seconds = 60
    return settings


# ── Utilities ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_emergency_email():
    """Sample emergency (flood) email."""
    return {
        "sender": "tenant@example.com",
        "subject": "WATER EVERYWHERE - EMERGENCY",
        "body": """URGENT - There is water pouring from the ceiling in the living room.
        It looks like a pipe has burst. This is happening right now.
        Please send someone immediately. Unit 402.""",
    }


@pytest.fixture
def sample_billing_email():
    """Sample low priority billing email."""
    return {
        "sender": "accounting@example.com",
        "subject": "Question about rent",
        "body": """Hi, I have a question about this month's rent invoice.
        It looks different from last month. Can you clarify the breakdown?
        Thanks, John""",
    }


@pytest.fixture
def sample_noise_email():
    """Sample noise complaint."""
    return {
        "sender": "upstairs@example.com",
        "subject": "Noise complaint",
        "body": """There is too much noise coming from Unit 402.
        It's 2am and the music is very loud. Please tell them to turn it down.""",
    }


@pytest.fixture
def sample_malformed_email():
    """Sample malformed/ambiguous email."""
    return {
        "sender": "unknown@example.com",
        "subject": "",
        "body": "XYZABC @#$% !!! ???",
    }
