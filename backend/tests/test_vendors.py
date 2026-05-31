"""Tests for vendor management endpoints."""
import uuid
import pytest
from httpx import AsyncClient

ORG_ID = str(uuid.uuid4())


@pytest.mark.asyncio
async def test_list_vendors_empty(async_client: AsyncClient):
    r = await async_client.get(f"/api/v1/vendors/?org_id={ORG_ID}")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_vendor(async_client: AsyncClient):
    payload = {"org_id": ORG_ID, "name": "Bob Plumbing", "email": "bob@example.com", "specialty": "plumbing"}
    r = await async_client.post("/api/v1/vendors/", json=payload)
    assert r.status_code == 201
    d = r.json()
    assert d["name"] == "Bob Plumbing"
    assert d["specialty"] == "plumbing"
    assert d["active"] is True


@pytest.mark.asyncio
async def test_create_vendor_invalid_specialty(async_client: AsyncClient):
    payload = {"org_id": ORG_ID, "name": "Bad", "email": "bad@example.com", "specialty": "roofing"}
    r = await async_client.post("/api/v1/vendors/", json=payload)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_soft_delete_vendor(async_client: AsyncClient):
    r = await async_client.post("/api/v1/vendors/", json={
        "org_id": ORG_ID, "name": "Del", "email": "del@example.com", "specialty": "general"
    })
    vid = r.json()["id"]
    r2 = await async_client.delete(f"/api/v1/vendors/{vid}")
    assert r2.status_code == 204
    r3 = await async_client.get(f"/api/v1/vendors/?org_id={ORG_ID}")
    assert all(v["id"] != vid for v in r3.json())
