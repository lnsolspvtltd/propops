"""Tests for POST /api/v1/auth/register and POST /api/v1/auth/login.

Uses an in-memory SQLite database (via aiosqlite) so no live Postgres is
required.  All tables are created from SQLAlchemy metadata at fixture setup.

Requires:
    pytest-asyncio >= 0.21
    httpx
    aiosqlite
    passlib[bcrypt]
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from passlib.context import CryptContext
from sqlalchemy import StaticPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.core.database import Base, get_db
from backend.main import app
from backend.models.organisation import Organisation
from backend.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def db_engine():
    """Fresh in-memory SQLite engine per test function."""
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(db_engine):
    """Async session bound to the test engine."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db_engine):
    """FastAPI AsyncClient with the test DB injected via dependency override."""
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db():
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def org(db_session: AsyncSession) -> Organisation:
    """Seed a single Organisation row."""
    o = Organisation(id=uuid.uuid4(), name="Test Org")
    db_session.add(o)
    await db_session.commit()
    await db_session.refresh(o)
    return o


@pytest.fixture
async def verified_user(db_session: AsyncSession, org: Organisation) -> User:
    """Seed a verified user for login tests."""
    u = User(
        id=uuid.uuid4(),
        org_id=org.id,
        email="alice@example.com",
        hashed_password=pwd_context.hash("correctpassword"),
        role="member",
        email_verified=True,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def unverified_user(db_session: AsyncSession, org: Organisation) -> User:
    """Seed an unverified user for login tests."""
    u = User(
        id=uuid.uuid4(),
        org_id=org.id,
        email="bob@example.com",
        hashed_password=pwd_context.hash("correctpassword"),
        role="member",
        email_verified=False,
    )
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_happy_path(client: AsyncClient, org: Organisation):
    """A new user can register against a valid org."""
    payload = {
        "email": "newuser@example.com",
        "password": "securepassword",
        "org_id": str(org.id),
        "role": "member",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "newuser@example.com"
    assert body["org_id"] == str(org.id)
    assert body["role"] == "member"
    assert "password" not in body
    assert "hashed_password" not in body
    # id must be a valid UUID
    uuid.UUID(body["id"])


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(
    client: AsyncClient, org: Organisation, verified_user: User
):
    """Registering the same email in the same org returns 409."""
    payload = {
        "email": verified_user.email,
        "password": "somepassword",
        "org_id": str(org.id),
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "email_already_registered"


@pytest.mark.asyncio
async def test_register_unknown_org_returns_404(client: AsyncClient):
    """Registering against a non-existent org returns 404."""
    payload = {
        "email": "ghost@example.com",
        "password": "ghostpassword",
        "org_id": str(uuid.uuid4()),
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "org_not_found"


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client: AsyncClient, org: Organisation):
    """Password shorter than 8 chars triggers Pydantic validation (422)."""
    payload = {
        "email": "short@example.com",
        "password": "seven7",
        "org_id": str(org.id),
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_register_different_orgs_same_email_allowed(
    client: AsyncClient, db_session: AsyncSession, org: Organisation, verified_user: User
):
    """The same email address may be registered in different orgs."""
    org2 = Organisation(id=uuid.uuid4(), name="Second Org")
    db_session.add(org2)
    await db_session.commit()
    await db_session.refresh(org2)

    payload = {
        "email": verified_user.email,
        "password": "differentpassword",
        "org_id": str(org2.id),
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_real_user_happy_path(client: AsyncClient, verified_user: User):
    """A verified user can log in and receives a JWT with correct claims."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": verified_user.email, "password": "correctpassword", "org_id": str(verified_user.org_id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    user_info = body["user"]
    assert user_info["email"] == verified_user.email
    assert user_info["org_id"] == str(verified_user.org_id)
    assert "password" not in str(body)
    assert "hashed_password" not in str(body)


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient, verified_user: User):
    """Wrong password returns 401."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": verified_user.email, "password": "wrongpassword", "org_id": str(verified_user.org_id)},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_unverified_user_returns_401(client: AsyncClient, unverified_user: User):
    """Unverified user returns generic 401 invalid_credentials — no response-body oracle."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": unverified_user.email, "password": "correctpassword", "org_id": str(unverified_user.org_id)},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client: AsyncClient):
    """Unknown email with no demo fallback should return 401."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "somepassword", "org_id": str(uuid.uuid4())},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_requires_org_id(client: AsyncClient):
    """Login without org_id returns 422 — field is required."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert response.status_code == 422  # org_id required


@pytest.mark.asyncio
async def test_login_jwt_contains_org_id(client: AsyncClient, verified_user: User):
    """The returned JWT must contain org_id in its payload (not from client input)."""
    from jose import jwt as jose_jwt

    from backend.core.config import settings

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": verified_user.email, "password": "correctpassword", "org_id": str(verified_user.org_id)},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = jose_jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert payload.get("org_id") == str(verified_user.org_id)
    assert payload.get("email") == verified_user.email
    assert "jti" in payload
