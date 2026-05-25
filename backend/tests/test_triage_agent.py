"""Tests for the AI triage agent."""
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import anthropic

from backend.ai.triage_agent import triage_message, TriageResult


class TestTriageAgent:
    """Test suite for AI triage classification."""

    @pytest.mark.asyncio
    async def test_triage_emergency_flood(self, mock_triage_response):
        """Test detection of emergency (flood) incident."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Mock the API response
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps(mock_triage_response)
            mock_client.messages.create.return_value = mock_response
            
            result = triage_message(
                message_body="WATER EVERYWHERE - pipe burst in ceiling. Help!",
                sender="tenant@example.com",
                subject="EMERGENCY"
            )
            
            assert result.success
            assert result.urgency == "HIGH"
            assert result.category == "maintenance"
            assert result.requires_vendor is True
            assert result.confidence > 0.9
            assert "plumbing" in result.tags

    @pytest.mark.asyncio
    async def test_triage_low_priority_billing(self, mock_triage_response):
        """Test classification of low priority billing inquiry."""
        billing_response = {
            "category": "billing",
            "urgency": "LOW",
            "title": "Rent invoice question",
            "summary": "Tenant asking about rent amount breakdown on this month's invoice.",
            "sentiment": "neutral",
            "unit_mentioned": None,
            "requires_vendor": False,
            "confidence": 0.88,
            "tags": ["billing", "inquiry"],
        }
        
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps(billing_response)
            mock_client.messages.create.return_value = mock_response
            
            result = triage_message(
                message_body="Can you explain why this month's rent is different? Last month was $2000, now it's $2100.",
                sender="accounting@example.com",
                subject="Rent question"
            )
            
            assert result.success
            assert result.urgency == "LOW"
            assert result.category == "billing"
            assert result.requires_vendor is False
            assert result.confidence > 0.8

    @pytest.mark.asyncio
    async def test_triage_noise_complaint(self, mock_triage_response):
        """Test classification of noise complaint."""
        noise_response = {
            "category": "noise",
            "urgency": "MEDIUM",
            "title": "Excessive noise complaint",
            "summary": "Neighbor complaining about loud music at 2am from adjacent unit.",
            "sentiment": "frustrated",
            "unit_mentioned": "402",
            "requires_vendor": False,
            "confidence": 0.91,
            "tags": ["noise", "complaint", "disturbance"],
        }
        
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps(noise_response)
            mock_client.messages.create.return_value = mock_response
            
            result = triage_message(
                message_body="There is loud music from Unit 402 at 2am. Please tell them to stop.",
                sender="neighbor@example.com",
                subject="Noise complaint"
            )
            
            assert result.success
            assert result.urgency == "MEDIUM"
            assert result.category == "noise"
            assert "noise" in result.tags

    @pytest.mark.asyncio
    async def test_triage_malformed_input(self):
        """Test graceful handling of malformed input."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Simulate JSON parse failure
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "INVALID JSON $$$ NOT VALID"
            mock_client.messages.create.return_value = mock_response
            
            result = triage_message(
                message_body="XYZABC @#$% !!! ???",
                sender="unknown@example.com",
                subject=""
            )
            
            # Should fallback to safe defaults
            assert result.success is False
            assert result.category == "general"
            assert result.urgency == "MEDIUM"
            assert result.confidence == 0.0
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_triage_api_timeout_fallback(self):
        """Test fallback behavior on API timeout."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # Simulate all retries failing
            mock_client.messages.create.side_effect = Exception("API timeout after retries")
            
            result = triage_message(
                message_body="Test message",
                sender="test@example.com",
                subject="Test"
            )
            
            # Should fallback to safe defaults
            assert result.success is False
            assert result.category == "general"
            assert result.urgency == "MEDIUM"
            assert "timeout" in result.error.lower() or "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_triage_rate_limit_retry(self):
        """Test retry logic on rate limit errors."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            # First two calls fail with rate limit, third succeeds
            valid_response = {
                "category": "maintenance",
                "urgency": "HIGH",
                "title": "Test incident",
                "summary": "Test summary",
                "sentiment": "neutral",
                "unit_mentioned": None,
                "requires_vendor": False,
                "confidence": 0.85,
                "tags": ["test"],
            }
            
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps(valid_response)
            
            mock_client.messages.create.side_effect = [
                anthropic.RateLimitError(response=MagicMock(status_code=429), body="Rate limit"),
                anthropic.RateLimitError(response=MagicMock(status_code=429), body="Rate limit"),
                mock_response,
            ]
            
            result = triage_message(
                message_body="Test message",
                sender="test@example.com",
                subject="Test"
            )
            
            assert result.success
            assert result.category == "maintenance"

    @pytest.mark.asyncio
    async def test_triage_empty_subject(self):
        """Test handling of empty/missing subject."""
        valid_response = {
            "category": "general",
            "urgency": "LOW",
            "title": "Inquiry from tenant",
            "summary": "General inquiry with no subject provided",
            "sentiment": "neutral",
            "unit_mentioned": None,
            "requires_vendor": False,
            "confidence": 0.65,
            "tags": ["inquiry"],
        }
        
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client
            
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps(valid_response)
            mock_client.messages.create.return_value = mock_response
            
            result = triage_message(
                message_body="Is anyone home?",
                sender="vendor@example.com",
                subject=""
            )
            
            assert result.success
            assert result.category == "general"

    @pytest.mark.asyncio
    async def test_triage_result_model(self):
        """Test TriageResult Pydantic model validation."""
        result = TriageResult(
            category="maintenance",
            urgency="HIGH",
            title="Test",
            summary="Test summary",
            sentiment="urgent",
            unit_mentioned="402",
            requires_vendor=True,
            confidence=0.95,
            tags=["test", "urgent"],
            model_used="claude-haiku-4-5",
            success=True,
        )
        
        assert result.category == "maintenance"
        assert result.urgency == "HIGH"
        assert result.confidence == 0.95
        assert len(result.tags) == 2