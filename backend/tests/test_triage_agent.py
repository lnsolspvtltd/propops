"""Tests for triage agent — classification and urgency scoring."""
import pytest
from unittest.mock import patch, MagicMock
import json
import anthropic

from backend.ai.triage_agent import triage_message, TriageResult, TRIAGE_SYSTEM_PROMPT


class TestTriageAgent:
    """Test suite for the triage agent."""

    @pytest.mark.asyncio
    async def test_triage_emergency_flood_detection(self):
        """Test EMERGENCY classification for flood/water emergency."""
        message = """
        URGENT: Water is pouring from the ceiling in unit 302!
        It looks like the pipe from the unit above has burst.
        Water is dripping onto our electronics.
        Please help immediately!
        """

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps({
                "category": "maintenance",
                "urgency": "EMERGENCY",
                "title": "Water leak from ceiling - urgent",
                "summary": "Tenant reports ceiling water leak from burst pipe above unit",
                "sentiment": "urgent",
                "unit_mentioned": "302",
                "requires_vendor": True,
                "confidence": 0.98,
                "tags": ["flood", "emergency", "pipe_burst"]
            })
            mock_client.messages.create.return_value = mock_response

            result = triage_message(message, sender="tenant@example.com", subject="WATER LEAK")

        assert result.urgency == "EMERGENCY"
        assert result.category == "maintenance"
        assert result.confidence == 0.98
        assert result.requires_vendor is True
        assert result.success is True
        assert "flood" in result.tags

    @pytest.mark.asyncio
    async def test_triage_low_priority_billing(self):
        """Test LOW classification for billing inquiries."""
        message = """
        Hi, I just have a question about my rent payment schedule.
        Could the rent be split into two payments per month instead of one?
        Thanks!
        """

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps({
                "category": "billing",
                "urgency": "LOW",
                "title": "Rent payment schedule inquiry",
                "summary": "Tenant asking about splitting monthly rent into two payments",
                "sentiment": "neutral",
                "unit_mentioned": None,
                "requires_vendor": False,
                "confidence": 0.92,
                "tags": ["billing", "payment", "inquiry"]
            })
            mock_client.messages.create.return_value = mock_response

            result = triage_message(message, sender="tenant@example.com", subject="Payment Question")

        assert result.urgency == "LOW"
        assert result.category == "billing"
        assert result.requires_vendor is False
        assert result.success is True

    @pytest.mark.asyncio
    async def test_triage_noise_complaint_classification(self):
        """Test MEDIUM classification for noise complaints."""
        message = """
        The tenant above me (unit 405) has been playing loud music until 2 AM every night this week.
        I work early mornings and can't sleep.
        This is becoming unbearable.
        """

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps({
                "category": "noise",
                "urgency": "MEDIUM",
                "title": "Noise complaint - late night music from unit 405",
                "summary": "Tenant complaining about loud music from adjacent unit during late hours",
                "sentiment": "frustrated",
                "unit_mentioned": "405",
                "requires_vendor": False,
                "confidence": 0.88,
                "tags": ["noise", "complaint", "neighbor_dispute"]
            })
            mock_client.messages.create.return_value = mock_response

            result = triage_message(message, sender="tenant@example.com", subject="Noise Complaint")

        assert result.urgency == "MEDIUM"
        assert result.category == "noise"
        assert result.sentiment == "frustrated"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_triage_malformed_input_fallback(self):
        """Test graceful handling of malformed/unusual input."""
        message = "!@#$%^&*()_+-=[]{}|;:',.<>?/`~"

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Simulate malformed response that causes JSON parse error
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "This is not JSON at all"
            mock_client.messages.create.return_value = mock_response

            result = triage_message(message, sender="unknown@example.com", subject="")

        assert result.success is False
        assert result.category == "general"
        assert result.urgency == "MEDIUM"
        assert result.confidence == 0.0
        assert "JSON parse failed" in result.error

    @pytest.mark.asyncio
    async def test_triage_api_timeout_fallback(self):
        """Test fallback behavior on API timeout."""
        message = "This is a normal message that should trigger a timeout"

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Simulate all retries exhausted (3 attempts)
            mock_client.messages.create.side_effect = anthropic.RateLimitError(
                "Rate limit exceeded", response=MagicMock(), body=""
            )

            result = triage_message(message, sender="tenant@example.com", subject="Test")

        assert result.success is False
        assert result.category == "general"
        assert result.urgency == "MEDIUM"
        assert "retry" in result.error.lower()

    @pytest.mark.asyncio
    async def test_triage_high_priority_no_heat(self):
        """Test HIGH classification for habitability issues."""
        message = """
        The heat stopped working in my apartment.
        It's -5°C outside and there's no heat at all.
        I have a 2-year-old and this is dangerous.
        """

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps({
                "category": "maintenance",
                "urgency": "HIGH",
                "title": "No heat in apartment - emergency",
                "summary": "Tenant reports complete heating failure in winter conditions with young child",
                "sentiment": "urgent",
                "unit_mentioned": None,
                "requires_vendor": True,
                "confidence": 0.99,
                "tags": ["heating", "habitability", "child_safety"]
            })
            mock_client.messages.create.return_value = mock_response

            result = triage_message(message, sender="tenant@example.com", subject="Heat Down")

        assert result.urgency == "HIGH"
        assert result.confidence == 0.99
        assert result.requires_vendor is True

    @pytest.mark.asyncio
    async def test_triage_input_truncation(self):
        """Test that very long messages are truncated."""
        long_message = "word " * 10000  # Create a very long message

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps({
                "category": "general",
                "urgency": "LOW",
                "title": "Very long message",
                "summary": "Long text input",
                "sentiment": "neutral",
                "confidence": 0.5,
                "tags": []
            })
            mock_client.messages.create.return_value = mock_response

            result = triage_message(long_message, sender="test@example.com")

        # Verify the call was made (the truncation happens in the agent)
        assert mock_client.messages.create.called
        # Check that the sent prompt doesn't exceed reasonable limits
        call_args = mock_client.messages.create.call_args
        prompt_text = call_args[1]["messages"][0]["content"]
        assert len(prompt_text) < 3000  # Should be truncated

    @pytest.mark.asyncio
    async def test_triage_confidence_scores(self):
        """Test that confidence scores are returned correctly."""
        message = "My sink is leaking"

        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = json.dumps({
                "category": "maintenance",
                "urgency": "MEDIUM",
                "title": "Leaking sink",
                "summary": "Plumbing leak under sink",
                "sentiment": "neutral",
                "confidence": 0.85,
                "tags": ["plumbing"]
            })
            mock_client.messages.create.return_value = mock_response

            result = triage_message(message)

        assert 0.0 <= result.confidence <= 1.0
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_triage_system_prompt_exists(self):
        """Test that system prompt is defined and contains key rules."""
        assert TRIAGE_SYSTEM_PROMPT is not None
        assert "EMERGENCY" in TRIAGE_SYSTEM_PROMPT
        assert "urgency" in TRIAGE_SYSTEM_PROMPT.lower()
        assert "JSON" in TRIAGE_SYSTEM_PROMPT
---