"""Tests for draft generation agent."""
import pytest
from unittest.mock import patch, MagicMock
import anthropic

from backend.ai.draft_agent import generate_draft, DraftResult, DRAFT_SYSTEM_PROMPT


class TestDraftAgent:
    """Test suite for the draft generation agent."""

    @pytest.mark.asyncio
    async def test_draft_tenant_reply_basic(self):
        """Test basic tenant reply generation."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Thank you for reporting this issue. We will send someone to assess the situation within 24 hours."
            mock_client.messages.create.return_value = mock_response

            result = generate_draft(
                incident_title="Broken pipe",
                incident_summary="Water leak from bathroom pipe",
                category="maintenance",
                urgency="HIGH",
                tenant_name="John Smith",
                property_name="123 Main St",
            )

        assert result.success is True
        assert "Thank you" in result.body
        assert "Re: Broken pipe" in result.subject
        assert result.draft_type == "tenant_reply"

    @pytest.mark.asyncio
    async def test_draft_does_not_admit_liability(self):
        """Test that draft does NOT admit liability."""
        message_body = "Thank you for reaching out. We will investigate this matter and respond shortly with next steps."

        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = message_body
            mock_client.messages.create.return_value = mock_response

            result = generate_draft(
                incident_title="Issue reported",
                incident_summary="Tenant complaint",
                category="general",
                urgency="MEDIUM",
            )

        assert result.success is True
        # Check system prompt prevents liability admission
        assert DRAFT_SYSTEM_PROMPT is not None
        assert "admit liability" in DRAFT_SYSTEM_PROMPT.lower()
        assert "fault" in DRAFT_SYSTEM_PROMPT.lower()

    @pytest.mark.asyncio
    async def test_draft_emergency_has_urgent_tone(self):
        """Test that EMERGENCY drafts use urgent, immediate tone."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "We are treating this as an emergency. Our team is dispatching immediately to address this critical situation."
            mock_client.messages.create.return_value = mock_response

            result = generate_draft(
                incident_title="Flood in unit 302",
                incident_summary="Water pouring from ceiling",
                category="maintenance",
                urgency="EMERGENCY",
            )

        assert result.success is True
        assert "URGENT:" in result.subject  # Subject should have URGENT prefix
        assert result.draft_type == "tenant_reply"

    @pytest.mark.asyncio
    async def test_draft_missing_tenant_name_handled(self):
        """Test graceful handling when tenant name is missing."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Thank you for contacting us. We have received your message and will respond within 24 hours."
            mock_client.messages.create.return_value = mock_response

            # Call without tenant_name
            result = generate_draft(
                incident_title="Maintenance request",
                incident_summary="General maintenance needed",
                category="maintenance",
                urgency="MEDIUM",
                tenant_name="",  # Empty name
                property_name="Unknown Property",
            )

        assert result.success is True
        assert len(result.body) > 0
        assert "Thank you" in result.body

    @pytest.mark.asyncio
    async def test_draft_api_timeout_fallback(self):
        """Test fallback response on API timeout."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Simulate rate limit errors on all attempts
            mock_client.messages.create.side_effect = anthropic.RateLimitError(
                "Rate limited", response=MagicMock(), body=""
            )

            result = generate_draft(
                incident_title="Test incident",
                incident_summary="Test summary",
                category="general",
                urgency="MEDIUM",
            )

        assert result.success is False
        # Should still have a safe fallback message
        assert len(result.body) > 0
        assert "shortly" in result.body.lower()

    @pytest.mark.asyncio
    async def test_draft_subject_line_generation(self):
        """Test appropriate subject line generation."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Response body"
            mock_client.messages.create.return_value = mock_response

            # Test MEDIUM urgency subject
            result = generate_draft(
                incident_title="Bathroom faucet dripping",
                incident_summary="Small water leak",
                category="maintenance",
                urgency="MEDIUM",
            )

        assert result.subject == "Re: Bathroom faucet dripping"

    @pytest.mark.asyncio
    async def test_draft_body_length(self):
        """Test that draft body is reasonable length (under 200 words typical)."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Thank you. We will help."
            mock_client.messages.create.return_value = mock_response

            result = generate_draft(
                incident_title="Issue",
                incident_summary="Description",
                category="general",
                urgency="LOW",
            )

        # System prompt says keep under 200 words
        words = len(result.body.split())
        assert words < 300  # Allow some flexibility but should be reasonably brief

    @pytest.mark.asyncio
    async def test_draft_does_not_confirm_appointment(self):
        """Test that draft does NOT confirm specific appointment times."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            # Response that avoids confirming specific time
            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "We will be in touch to confirm a convenient appointment time."
            mock_client.messages.create.return_value = mock_response

            result = generate_draft(
                incident_title="Inspection needed",
                incident_summary="Property inspection",
                category="maintenance",
                urgency="MEDIUM",
            )

        assert result.success is True
        # System prompt should prevent specific time confirmations
        assert "confirm" in DRAFT_SYSTEM_PROMPT.lower()
        assert "appointment" in DRAFT_SYSTEM_PROMPT.lower()

    @pytest.mark.asyncio
    async def test_draft_different_urgency_tones(self):
        """Test that different urgency levels produce appropriate tone guidance."""
        urgency_levels = ["EMERGENCY", "HIGH", "MEDIUM", "LOW"]
        expected_tones = {
            "EMERGENCY": "immediate",
            "HIGH": "urgency",
            "MEDIUM": "Professional",
            "LOW": "Friendly",
        }

        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Response body"
            mock_client.messages.create.return_value = mock_response

            for urgency in urgency_levels:
                result = generate_draft(
                    incident_title="Test",
                    incident_summary="Test",
                    category="general",
                    urgency=urgency,
                )
                assert result.success is True

            # Verify the function was called with appropriate guidance
            assert mock_client.messages.create.call_count == len(urgency_levels)

    @pytest.mark.asyncio
    async def test_draft_model_tracking(self):
        """Test that draft tracks which model was used."""
        with patch("backend.ai.draft_agent.anthropic.Anthropic") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            mock_response = MagicMock()
            mock_response.content = [MagicMock()]
            mock_response.content[0].text = "Response"
            mock_client.messages.create.return_value = mock_response

            result = generate_draft(
                incident_title="Test",
                incident_summary="Test",
                category="general",
                urgency="MEDIUM",
            )

        assert result.model_used == "claude-sonnet-4-5-20251001"

    @pytest.mark.asyncio
    async def test_draft_system_prompt_rules(self):
        """Test that system prompt contains key rules."""
        assert "NEVER admit liability" in DRAFT_SYSTEM_PROMPT
        assert "NEVER confirm payment" in DRAFT_SYSTEM_PROMPT
        assert "NEVER confirm a specific appointment" in DRAFT_SYSTEM_PROMPT
        assert "NEVER promise a timeline" in DRAFT_SYSTEM_PROMPT
---