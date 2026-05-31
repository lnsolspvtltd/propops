"""Tests for tenant management endpoints and context resolver."""
import uuid
import pytest
from httpx import AsyncClient

ORG_ID = str(uuid.uuid4())


@pytest.mark.asyncio
async def test_list_tenants_empty(async_client: AsyncClient):
    r = await async_client.get(f"/api/v1/tenants/?org_id={ORG_ID}")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_tenant(async_client: AsyncClient):
    r = await async_client.post("/api/v1/tenants/", json={
        "org_id": ORG_ID, "name": "Alice", "email": "alice@example.com"
    })
    assert r.status_code == 201
    d = r.json()
    assert d["name"] == "Alice"
    assert d["email"] == "alice@example.com"
    assert d["active"] is True


@pytest.mark.asyncio
async def test_soft_delete_tenant(async_client: AsyncClient):
    r = await async_client.post("/api/v1/tenants/", json={
        "org_id": ORG_ID, "name": "Del", "email": "del@example.com"
    })
    tid = r.json()["id"]
    r2 = await async_client.delete(f"/api/v1/tenants/{tid}")
    assert r2.status_code == 204
    r3 = await async_client.get(f"/api/v1/tenants/?org_id={ORG_ID}")
    assert all(t["id"] != tid for t in r3.json())


@pytest.mark.asyncio
async def test_list_units_empty(async_client: AsyncClient):
    r = await async_client.get(f"/api/v1/units/?org_id={ORG_ID}")
    assert r.status_code == 200
    assert r.json() == []
