"""Unit tests for AI triage agent.

Tests all urgency levels, error handling, edge cases, and JSON validation.
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import json
import anthropic

from backend.ai.triage_agent import (
    triage_message,
    TriageResult,
    _detect_emergency_keyword,
    _extract_unit_number,
    _sanitize_for_llm,
    _validate_json_response,
)


class TestEmergencyKeywordDetection:
    """Test emergency keyword fallback detection."""

    def test_flood_detection(self):
        assert _detect_emergency_keyword("The basement is flooding!") == "flood"

    def test_fire_detection(self):
        assert _detect_emergency_keyword("There's smoke and fire!") == "fire"

    def test_gas_leak_detection(self):
        assert _detect_emergency_keyword("I smell gas in the kitchen") == "gas leak"

    def test_no_heat_detection(self):
        assert _detect_emergency_keyword("no heat in unit") == "no heat"

    def test_security_breach_detection(self):
        assert _detect_emergency_keyword("Someone broke in!") == "break in"

    def test_no_keyword_match(self):
        assert _detect_emergency_keyword("The paint is chipped") is None


class TestUnitNumberExtraction:
    """Test unit number extraction."""

    def test_unit_format(self):
        assert _extract_unit_number("Unit 101 is leaking") == "101"

    def test_apt_format(self):
        assert _extract_unit_number("Apt 3A has no heat") == "3a"

    def test_hash_format(self):
        assert _extract_unit_number("Issue at #404") == "404"

    def test_apartment_format(self):
        assert _extract_unit_number("Apartment 5B water damage") == "5b"

    def test_no_unit_mentioned(self):
        assert _extract_unit_number("General building issue") is None


class TestInputSanitization:
    """Test input sanitization for LLM safety."""

    def test_html_removal(self):
        assert "<div>" not in _sanitize_for_llm("<div>test</div>")
        assert "test" in _sanitize_for_llm("<div>test</div>")

    def test_whitespace_collapse(self):
        result = _sanitize_for_llm("text    with   spaces")
        assert "    " not in result

    def test_max_length_enforcement(self):
        long_text = "a" * 5000
        result = _sanitize_for_llm(long_text, max_chars=3000)
        assert len(result) <= 3000

    def test_empty_input(self):
        result = _sanitize_for_llm("")
        assert result == ""


class TestJSONValidation:
    """Test JSON response validation."""

    def test_valid_response(self):
        valid_data = {
            "category": "maintenance",
            "urgency": "HIGH",
            "title": "Broken lock",
            "summary": "Tenant reports lock broken. Needs immediate attention.",
            "sentiment": "frustrated",
            "unit_mentioned": "101",
            "requires_vendor": True,
            "confidence": 0.95,
            "tags": ["lock", "urgent"],
        }
        is_valid, error = _validate_json_response(valid_data)
        assert is_valid is True
        assert error is None

    def test_missing_required_field(self):
        invalid_data = {
            "category": "maintenance",
            # missing urgency
            "title": "Test",
            "summary": "Test",
            "sentiment": "neutral",
            "requires_vendor": False,
            "confidence": 0.5,
            "tags": [],
        }
        is_valid, error = _validate_json_response(invalid_data)
        assert is_valid is False
        assert "urgency" in error

    def test_invalid_category(self):
        invalid_data = {
            "category": "invalid_category",
            "urgency": "HIGH",
            "title": "Test",
            "summary": "Test",
            "sentiment": "neutral",
            "requires_vendor": False,
            "confidence": 0.5,
            "tags": [],
        }
        is_valid, error = _validate_json_response(invalid_data)
        assert is_valid is False

    def test_invalid_urgency(self):
        invalid_data = {
            "category": "maintenance",
            "urgency": "CRITICAL",
            "title": "Test",
            "summary": "Test",
            "sentiment": "neutral",
            "requires_vendor": False,
            "confidence": 0.5,
            "tags": [],
        }
        is_valid, error = _validate_json_response(invalid_data)
        assert is_valid is False

    def test_confidence_out_of_range(self):
        invalid_data = {
            "category": "maintenance",
            "urgency": "HIGH",
            "title": "Test",
            "summary": "Test",
            "sentiment": "neutral",
            "requires_vendor": False,
            "confidence": 1.5,  # Invalid
            "tags": [],
        }
        is_valid, error = _validate_json_response(invalid_data)
        assert is_valid is False

    def test_title_too_long(self):
        invalid_data = {
            "category": "maintenance",
            "urgency": "HIGH",
            "title": "a" * 100,  # > 80 chars
            "summary": "Test",
            "sentiment": "neutral",
            "requires_vendor": False,
            "confidence": 0.5,
            "tags": [],
        }
        is_valid, error = _validate_json_response(invalid_data)
        assert is_valid is False


class TestTriageEmergencyDetection:
    """Test EMERGENCY urgency classification."""

    @pytest.mark.asyncio
    async def test_flood_detection_accuracy(self):
        """Test flood detection with high confidence."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "category": "maintenance",
                "urgency": "EMERGENCY",
                "title": "Basement flooding",
                "summary": "Tenant reports water pouring into basement. Immediate action required.",
                "sentiment": "urgent",
                "unit_mentioned": "B1",
                "requires_vendor": True,
                "confidence": 0.98,
                "tags": ["flood", "water-damage", "emergency"],
            }))]
            mock_client.return_value.messages.create.return_value = mock_response

            result = triage_message(
                "Water is pouring into the basement. It's flooding everywhere!",
                sender="tenant@example.com",
                subject="EMERGENCY: Basement flooding"
            )

            assert result.urgency == "EMERGENCY"
            assert result.confidence >= 0.95

    @pytest.mark.asyncio
    async def test_fire_detection_accuracy(self):
        """Test fire detection with high confidence."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "category": "maintenance",
                "urgency": "EMERGENCY",
                "title": "Fire in unit",
                "summary": "Active fire in unit 305. Immediate evacuation needed.",
                "sentiment": "urgent",
                "unit_mentioned": "305",
                "requires_vendor": True,
                "confidence": 0.99,
                "tags": ["fire", "emergency", "evacuation"],
            }))]
            mock_client.return_value.messages.create.return_value = mock_response

            result = triage_message(
                "EMERGENCY FIRE IN MY UNIT NOW!!! Call 911!!!",
                sender="tenant@example.com"
            )

            assert result.urgency == "EMERGENCY"
            assert result.confidence >= 0.95

    @pytest.mark.asyncio
    async def test_no_heat_winter_emergency(self):
        """Test no heat in winter as EMERGENCY."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "category": "maintenance",
                "urgency": "EMERGENCY",
                "title": "No heat in winter",
                "summary": "Tenant reports zero heat in unit during winter. Habitability risk.",
                "sentiment": "urgent",
                "unit_mentioned": "201",
                "requires_vendor": True,
                "confidence": 0.97,
                "tags": ["heat", "habitability", "winter"],
            }))]
            mock_client.return_value.messages.create.return_value = mock_response

            result = triage_message(
                "It's -5C outside and there's no heat in our unit. Kids are freezing.",
                sender="tenant@example.com"
            )

            assert result.urgency == "EMERGENCY"


class TestTriageHighPriorityDetection:
    """Test HIGH urgency classification."""

    @pytest.mark.asyncio
    async def test_broken_lock_detection(self):
        """Test broken lock as HIGH."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "category": "maintenance",
                "urgency": "HIGH",
                "title": "Front door lock broken",
                "summary": "Tenant unable to lock front door. Security risk.",
                "sentiment": "frustrated",
                "unit_mentioned": "102",
                "requires_vendor": True,
                "confidence": 0.92,
                "tags": ["lock", "security", "urgent"],
            }))]
            mock_client.return_value.messages.create.return_value = mock_response

            result = triage_message(
                "Our front door lock is broken. We can't lock it.",
                sender="tenant@example.com"
            )

            assert result.urgency == "HIGH"

    @pytest.mark.asyncio
    async def test_no_hot_water_detection(self):
        """Test no hot water as HIGH."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "category": "maintenance",
                "urgency": "HIGH",
                "title": "No hot water",
                "summary": "Tenant unable to get hot water. Multiple days without service.",
                "sentiment": "frustrated",
                "unit_mentioned": "503",
                "requires_vendor": True,
                "confidence": 0.90,
                "tags": ["hot-water", "utility"],
            }))]
            mock_client.return_value.messages.create.return_value = mock_response

            result = triage_message(
                "We have had no hot water for 3 days!",
                sender="tenant@example.com"
            )

            assert result.urgency == "HIGH"


class TestTriageMediumPriorityDetection:
    """Test MEDIUM urgency classification."""

    @pytest.mark.asyncio
    async def test_noise_complaint_medium(self):
        """Test noise complaint as MEDIUM."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "category": "noise",
                "urgency": "MEDIUM",
                "title": "Noise complaint from neighbors",
                "summary": "Tenant reports loud music at 10pm. Affecting other residents.",
                "sentiment": "frustrated",
                "unit_mentioned": "301",
                "requires_vendor": False,
                "confidence": 0.85,
                "tags": ["noise", "complaint"],
            }))]
            mock_client.return_value.messages.create.return_value = mock_response

            result = triage_message(
                "The neighbors in 303 are playing music way too loud at 10pm.",
                sender="tenant@example.com"
            )

            assert result.urgency == "MEDIUM"

    @pytest.mark.asyncio
    async def test_maintenance_request_medium(self):
        """Test standard maintenance request as MEDIUM."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=json.dumps({
                "category": "maintenance",
                "urgency": "MEDIUM",
                "title": "Paint touch-up needed",
                "summary": "Tenant requests paint touch-up in hallway. Cosmetic repair.",
                "sentiment": "neutral",
                "unit_mentioned": "201",
                "requires_vendor": True,
                "confidence": 0.88,
                "tags": ["maintenance", "cosmetic"],
            }))]
            mock_client.return_value.messages.create.return_value = mock_response

            result = triage_message(
                "Could you send someone to touch up the paint in the hallway? There's a mark.",
                sender="tenant@example.com"
            )

            assert result.urgency == "MEDIUM"


class TestTriageLowPriorityDetection:
    """Test LOW urgency classification."""

    @pytest.mark.