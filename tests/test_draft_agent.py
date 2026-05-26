"""Unit tests for AI draft generation and safety validation."""
import pytest
from backend.ai.draft_agent import (
    scan_for_safety_violations,
    DraftResult,
    LIABILITY_PATTERNS,
    FINANCIAL_CONFIRMATION_PATTERNS,
    TIME_CONFIRMATION_PATTERNS,
)


class TestScanForSafetyViolations:
    """Test safety pattern detection."""
    
    def test_detects_liability_admission(self):
        """Should detect liability admissions."""
        text = "We accept responsibility for the damage."
        violations = scan_for_safety_violations(text)
        assert len(violations) > 0
        assert any("Liability" in v for v in violations)
    
    def test_detects_fault_admission(self):
        """Should detect fault admissions."""
        text = "This is our mistake and we apologize."
        violations = scan_for_safety_violations(text)
        assert len(violations) > 0
    
    def test_detects_financial_confirmation(self):
        """Should detect financial confirmations."""
        text = "We confirm your deposit of $2,500 has been received."
        violations = scan_for_safety_violations(text)
        assert len(violations) > 0
        assert any("Financial" in v for v in violations)
    
    def test_detects_time_confirmation(self):
        """Should detect specific time confirmations."""
        text = "Our technician will arrive on Monday at 2:30 PM."
        violations = scan_for_safety_violations(text)
        assert len(violations) > 0
        assert any("time" in v.lower() for v in violations)
    
    def test_allows_safe_text(self):
        """Should allow text with no violations."""
        text = "Thank you for reporting this issue. We will investigate and contact you within 24 hours."
        violations = scan_for_safety_violations(text)
        assert len(violations) == 0
    
    def test_case_insensitive(self):
        """Should detect violations regardless of case."""
        text = "WE ACCEPT FULL RESPONSIBILITY for this matter."
        violations = scan_for_safety_violations(text)
        assert len(violations) > 0
    
    def test_detects_multiple_violations(self):
        """Should detect multiple different violation types."""
        text = "We admit our error. We confirm receipt of $5000. We will arrive at 3 PM."
        violations = scan_for_safety_violations(text)
        assert len(violations) >= 3


class TestDraftResult:
    """Test DraftResult model."""
    
    def test_success_result(self):
        """Should create successful result."""
        result = DraftResult(
            success=True,
            body="Thank you for contacting us.",
            subject="Re: Maintenance Request"
        )
        assert result.success is True
        assert result.body == "Thank you for contacting us."
        assert result.error is None
        assert result.safety_issues == []
    
    def test_error_result(self):
        """Should create error result."""
        result = DraftResult(
            success=False,
            error="API key not configured"
        )
        assert result.success is False
        assert result.error == "API key not configured"
        assert result.body is None
    
    def test_result_with_safety_issues(self):
        """Should include safety issues in result."""
        result = DraftResult(
            success=False,
            error="Draft rejected due to safety violations",
            safety_issues=["Liability admission detected"]
        )
        assert len(result.safety_issues) == 1
        assert "Liability" in result.safety_issues[0]
---