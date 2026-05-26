"""Unit tests for approval routes."""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from backend.api.routes.approvals import router
from backend.models.incident import AIDraft, Incident


@pytest.fixture
def mock_db():
    """Mock async DB session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def app():
    """FastAPI test app with approvals router."""
    app = FastAPI()
    app.include_router(router, prefix="/approvals", tags=["approvals"])
    return app


class TestRejectDraft:
    """Test reject_draft endpoint."""
    
    @pytest.mark.asyncio
    async def test_reject_records_rejected_by_and_timestamp(self, mock_db):
        """reject_draft should record rejector identity and rejection timestamp."""
        draft_id = str(uuid4())
        draft = AsyncMock(spec=AIDraft)
        draft.id = draft_id
        draft.status = "pending"
        
        # Mock DB execute to return the draft
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = draft
        mock_db.execute.return_value = mock_result
        
        from backend.api.routes.approvals import reject_draft, RejectRequest
        
        req = RejectRequest(reason="Does not match policy")
        
        with patch("backend.api.routes.approvals.get_db", return_value=mock_db):
            result = await reject_draft(draft_id, req, db=mock_db)
        
        # Verify audit fields were set
        assert draft.status == "rejected"
        assert draft.rejected_by == "admin"
        assert draft.rejected_at is not None
        assert isinstance(draft.rejected_at, datetime)
        assert draft