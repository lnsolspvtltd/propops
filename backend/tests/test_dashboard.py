from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from .db import get_db
from .models import Organization, Property, Unit, Incident, AI_Draft

def create_test_db():
    # Create a test database connection and session
    engine = create_async_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return AsyncSession(bind=engine), SessionLocal

def create_test_data(session):
    # Create some test data for the database
    org1 = Organization(name="Test Org 1", email_domain="test.org")
    prop1 = Property(org_id=org1.id, name="Test Building 1", address="123 Test St")
    unit1 = Unit(property_id=prop1.id, unit_number="Apt 4B", tenant_name="John Smith")
    incident1 = Incident(
        org_id=org1.id,
        property_id=prop1.id,
        unit_id=unit1.id,
        title="Water leak in kitchen",
        category="maintenance",
        urgency="high",
        status="open"
    )
    ai_draft1 = AI_Draft(
        incident_id=incident1.id,
        org_id=org1.id,
        draft_type="tenant_reply",
        subject="Test Draft",
        body="This is a test draft.",
        recipient_email="john.smith@test.org",
        status="approved"
    )
    session.add_all([org1, prop1, unit1, incident1, ai_draft1])
    session.commit()

client = TestClient(TestApp())

@pytest.fixture
async def mock_db():
    """Mock async DB session."""
    db = AsyncMock()
    db.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    return db

@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

@pytest.fixture
async def session():
    """Create a test database session."""
    engine, SessionLocal = create_test_db()
    await SessionLocal().execute("DELETE FROM incidents")
    await SessionLocal().commit()
    create_test_data(SessionLocal())
    async with SessionLocal() as s:
        yield s
    await engine.dispose()

@pytest.mark.asyncio
async def test_get_dashboard_stats(client, mock_db):
    with patch("backend.api.routes.dashboard.get_db", return_value=mock_db):
        response = await client.get("/api/v1/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, dict)
    assert "open_incidents" in data
    assert "awaiting_approval" in data
    assert "resolved_this_week" in data
    assert "avg_response_hours" in data
    assert "top_categories" in data
    assert "recent_incidents" in data

# Add more tests as needed
```

---

### SECTION 15 — ENV VARS NEEDED

No new environment variables are needed for this task.

---

### SECTION 16 — MIGRATION NEEDED

No database migrations are needed for this task.

---

### SECTION 17 — KNOWN LIMITATIONS

- The current implementation assumes that the `ai_drafts` table has a `created_at` column, which is not explicitly defined in the provided schema. This may need to be added if it's missing.
- The current implementation does not handle cases where there are no incidents or AI drafts for certain categories or statuses.

---

### SECTION 18 — SECURITY REVIEW NEEDED

No security review is needed for this task as it only involves database queries and API responses, which do not involve sensitive data.