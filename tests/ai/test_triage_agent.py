"""Tests for triage agent classification."""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from backend.ai.triage_agent import (
    classify_message,
    TriageResult,
    EMERGENCY_KEYWORDS,
    _fallback_triage,
)


@pytest.mark.asyncio
async def test_classify_message_success():
    """Test successful classification with valid LLM response."""
    message = "The basement is flooding with water!"
    
    valid_response = {
        "category": "maintenance",
        "urgency": "EMERGENCY",
        "title": "Basement flooding detected",
        "summary": "Tenant reports water flooding in basement. Immediate action required to prevent property damage.",
        "sentiment": "urgent",
        "unit_mentioned": None,
        "requires_vendor": True,
        "confidence": 0.98,
        "tags": ["water-damage", "emergency", "flood"]
    }
    
    with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps(valid_response))]
        mock_client.messages.create.return_value = mock_response
        
        result = await classify_message(message)
        
        assert result.urgency == "EMERGENCY"
        assert result.category == "maintenance"
        assert result.confidence >= 0.95


@pytest.mark.asyncio
async def test_classify_message_with_markdown():
    """Test classification handles markdown code blocks in response."""
    message = "No hot water in unit 3B"
    
    valid_response = {
        "category": "maintenance",
        "urgency": "HIGH",
        "title": "No hot water reported",
        "summary": "Tenant in unit 3B reports no hot water. Requires HVAC/plumbing vendor visit.",
        "sentiment": "frustrated",
        "unit_mentioned": "3B",
        "requires_vendor": True,
        "confidence": 0.92,
        "tags": ["hot-water", "plumbing", "high-priority"]
    }
    
    # Response wrapped in markdown code blocks (common from LLM)
    markdown_response = f"```json\n{json.dumps(valid_response)}\n```"
    
    with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_anthropic:
        mock_client = MagicMock()
        mock_anthropic.return_value = mock_client
        
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=markdown_response)]
        mock_client.messages.create.return_value = mock_response
        
        result = await classify_message(message)
        
        assert result.urgency == "HIGH"
        assert result.unit_mentioned == "3B"


@pytest.mark.asyncio
async def test