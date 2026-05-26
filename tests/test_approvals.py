"""Unit tests for approval queue API."""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from httpx import AsyncClient
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.routes.approvals import (
    router,
    approve_draft,
    reject_draft,
    get_current_user_id,
    ApproveRequest,
    RejectRequest,
)
from