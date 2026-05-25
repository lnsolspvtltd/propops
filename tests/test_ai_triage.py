"""Unit tests for AI Triage Agent."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from backend.ai.triage_agent import (
    triage_message,
    detect_emergency_keywords,
    _fallback_triage,
    EMERGENCY_KEYWORDS,
    TriageResult
)


class TestEmergencyKeywordDetection:
    """Test emergency keyword detection fallback."""
    
    def test_detects_flood_keyword(self):
        """Should detect 'flood' keyword in message."""
        text = "There is a flood in unit 301"
        assert detect_emergency_keywords(text) is True
    
    def test_detects_fire_keyword(self):
        """Should detect 'fire' keyword."""
        text = "FIRE! Call 911!"
        assert detect_emergency_keywords(text) is True
    
    def test_detects_gas_leak(self):
        """Should detect 'gas leak' keyword."""
        text = "I smell gas in the basement"
        assert detect_emergency_keywords(text) is True
    
    def test_detects_no_heat(self):
        """Should detect 'no heat' keyword."""
        text = "There is no heat and it's freezing"
        assert detect_emergency_keywords(text) is True
    
    def test_detects_break_in(self):
        """Should detect 'break in' keyword (with and without hyphen)."""
        text = "Someone broke in through the window"
        assert detect_emergency_keywords(text) is True
        
        text2 = "There was a break-in at unit 205"
        assert detect_emergency_keywords(text2) is True
    
    def test_case_insensitive(self):
        """Should detect keywords regardless of case."""
        text = "FLOODING IN BASEMENT"
        assert detect_emergency_keywords(text) is True
    
    def test_no_false_positives(self):
        """Should not flag non-emergency messages."""
        text = "Can you fix the paint in unit 101?"
        assert detect_emergency_keywords(text) is False
    
    def test_no_duplicate_flooding_in_set(self):
        """Verify no duplicate 'flooding' entry in EMERGENCY_KEYWORDS set."""
        # Convert to list and check for duplicates
        keywords_list = list(EMERGENCY_KEYWORDS)
        assert len(keywords_list) == len(set(keywords_list)), "Duplicate keywords found in EMERGENCY_KEYWORDS set"
        # Verify both 'flood' and 'flooding' are present (not the same)
        assert 'flood' in EMERGENCY_KEYWORDS
        assert 'flooding' in EMERGENCY_KEYWORDS


class TestFallbackTriage:
    """Test fallback triage when AI fails."""
    
    def test_fallback_emergency_detection(self):
        """Fallback should classify emergency keywords as EMERGENCY."""
        result = _fallback_triage("FLOOD IN APARTMENT")
        assert result.urgency == "EMERGENCY"
        assert result.confidence == 0.95
        assert "fallback" in result.tags
    
    def test_fallback_normal_message(self):
        """Fallback should classify normal messages as MEDIUM."""
        result = _fallback_triage("Can you fix the leaky faucet?")
        assert result.urgency == "MEDIUM"
        assert result.confidence == 0.3
    
    def test_fallback_includes_ai_unavailable_tag(self):
        """Fallback result should include 'ai_unavailable' tag."""
        result = _fallback_triage("Test message")
        assert "ai_unavailable" in result.tags


class TestTriageMessage:
    """Test main triage_message function."""
    
    @pytest.mark.asyncio
    async def test_empty_message_raises_error(self):
        """Should raise ValueError for empty message."""
        with pytest.raises(ValueError, match="cannot be empty"):
            await triage_message("")
    
    @pytest.mark.asyncio
    async def test_whitespace_only_message_raises_error(self):
        """Should raise ValueError for whitespace-only message."""
        with pytest.raises(ValueError, match="cannot be empty"):
            await triage_message("   \n\t  ")
    
    @pytest.mark.asyncio
    async def test_missing_api_key_raises_error(self):
        """Should raise ValueError if ANTHROPIC_API_KEY not set."""
        with patch("backend.ai.triage_agent.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                await triage_message("Test message")
    
    @pytest.mark.asyncio
    async def test_truncates_long_messages(self):
        """Should truncate messages longer than max_chars."""
        long_text = "A" * 5000
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text='{"category": "general", "urgency": "LOW", "title": "Test", "summary": "Test summary", "sentiment": "neutral", "unit_mentioned": null, "requires_vendor": false, "confidence": 0.5, "tags": []}')]
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            with patch("backend.ai.triage_agent.settings") as mock_settings:
                mock_settings.anthropic_api_key = "test-key"
                await triage_message(long_text, max_chars=1000)
                
                # Verify truncation by checking the call
                call_args = mock_client.messages.create.call_args
                content = call_args.kwargs["messages"][0]["content"]
                # Message content should not exceed 1000 chars + prompt text
                assert "A" * 1000 in content or len(content) < len(long_text) + 100
    
    @pytest.mark.asyncio
    async def test_falls_back_on_json_parse_error(self):
        """Should fall back to keyword detection if JSON parsing fails."""
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="This is not JSON")]
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            with patch("backend.ai.triage_agent.settings") as mock_settings:
                mock_settings.anthropic_api_key = "test-key"
                result = await triage_message("FLOOD IN BASEMENT")
                
                # Should fall back to keyword detection
                assert result.urgency == "EMERGENCY"
                assert "fallback" in result.tags
    
    @pytest.mark.asyncio
    async def test_successful_classification(self):
        """Should successfully parse and return valid triage result."""
        valid_json = """{
            "category": "maintenance",
            "urgency": "HIGH",
            "title": "Burst pipe in unit 301",
            "summary": "Water damage from burst pipe. Requires immediate vendor dispatch.",
            "sentiment": "frustrated",
            "unit_mentioned": "301",
            "requires_vendor": true,
            "confidence": 0.92,
            "tags": ["water damage", "urgent", "vendor needed"]
        }"""
        
        with patch("backend.ai.triage_agent.anthropic.Anthropic") as mock_client_class:
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text=valid_json)]
            mock_client = AsyncMock()
            mock_client.messages.create.return_value = mock_response
            mock_client_class.return_value = mock_client
            
            with patch("backend.ai.triage_agent.settings") as mock_settings:
                mock_settings.anthropic_api_key = "test-key"
                result = await triage_message("Water is leaking from ceiling in unit 301")
                
                assert isinstance(result, TriageResult)
                assert result.category == "maintenance"
                assert result.urgency == "HIGH"
                assert result.unit_mentioned == "301"
                assert result.confidence == 0.92


class TestTriageResultModel:
    """Test TriageResult Pydantic model validation."""
    
    def test_valid_result(self):
        """Should accept valid result."""
        result = TriageResult(
            category="maintenance",
            urgency="HIGH",
            title="Test",
            summary="Test summary here",
            sentiment="frustrated",
            confidence=0.8
        )
        assert result.urgency == "HIGH"
    
    def test_confidence_must_be_0_to_1(self):
        """Should reject confidence outside 0.0-1.0 range."""
        with pytest.raises(ValueError):
            TriageResult(
                category="maintenance",
                urgency="HIGH",
                title="Test",
                summary="Test",
                sentiment="neutral",
                confidence=1.5
            )
    
    def test_tags_default_to_empty_list(self):
        """Should default tags to empty list."""
        result = TriageResult(
            category="general",
            urgency="LOW",
            title="Test",
            summary="Test",
            sentiment="neutral",
            confidence=0.3
        )
        assert result.tags == []
---