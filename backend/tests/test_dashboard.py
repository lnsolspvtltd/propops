"""Tests for dashboard stats endpoint."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dashboard_stats_empty(async_client: AsyncClient):
    """Returns zeros when DB has no data."""
    r = await async_client.get("/api/v1/dashboard/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["open_incidents"] == 0
    assert d["awaiting_approval"] == 0
    assert d["resolved_this_week"] == 0
    assert d["avg_response_hours"] == 0.0
    assert d["top_categories"] == []
    assert d["recent_incidents"] == []


@pytest.mark.asyncio
async def test_dashboard_stats_fields(async_client: AsyncClient):
    """Response has all required fields."""
    r = await async_client.get("/api/v1/dashboard/stats")
    assert r.status_code == 200
    required = {"open_incidents","awaiting_approval","resolved_this_week",
                "avg_response_hours","top_categories","recent_incidents"}
    assert required.issubset(r.json().keys())