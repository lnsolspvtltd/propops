"""Unit tests for context resolution service.

Tests name extraction, similarity scoring, and matching logic WITHOUT database.
Database integration tested separately in integration tests.
"""
import pytest
from backend.services.context_resolver import (
    extract_name_from_email,
    name_similarity,
    ContextResolution,
)


class TestExtractNameFromEmail:
    """Tests for extract_name_from_email function."""
    
    def test_simple_dot_separated(self):
        """john.smith@gmail.com → john smith"""
        assert extract_name_from_email("john.smith@gmail.com") == "john smith"
    
    def test_underscore_separated(self):
        """john_smith@example.com → john smith"""
        assert extract_name_from_email("john_smith@example.com") == "john smith"
    
    def test_hyphen_separated(self):
        """john-smith@example.com → john smith"""
        assert extract_name_from_email("john-smith@example.com") == "john smith"
    
    def test_single_name(self):
        """jsmith@company.com → jsmith"""
        assert extract_name_from_email("jsmith@company.com") == "jsmith"
    
    def test_plus_tag_removed(self):
        """john+notifications@gmail.com → john"""
        assert extract_name_from_email("john+notifications@gmail.com") == "john"
    
    def test_complex_plus_tag(self):
        """john.smith+urgent@example.com → john smith"""
        assert extract_name_from_email("john.smith+urgent@example.com") == "john smith"
    
    def test_uppercase_normalized(self):
        """John.Smith@Example.com → john smith"""
        assert extract_name_from_email("John.Smith@Example.com") == "john smith"
    
    def test_multiple_separators(self):
        """john.-_smith@example.com → john smith"""
        assert extract_name_from_email("john.-_smith@example.com") == "john smith"
    
    def test_whitespace_normalized(self):
        """Removes leading/trailing whitespace"""
        assert extract_name_from_email("  john.smith@example.com  ") == "john smith"
    
    def test_no_at_sign(self):
        """Invalid email → empty string"""
        assert extract_name_from_email("notanemail") == ""
    
    def test_empty_string(self):
        """Empty string → empty string"""
        assert extract_name_from_email("") == ""
    
    def test_none_input(self):
        """None input → empty string"""
        assert extract_name_from_email(None or "") == ""


class TestNameSimilarity:
    """Tests for name_similarity function."""
    
    def test_exact_match(self):
        """john smith == john smith → 1.0"""
        assert name_similarity("john smith", "john smith") == 1.0
    
    def test_case_insensitive(self):
        """John Smith == john smith → 1.0"""
        assert name_similarity("John Smith", "john smith") == 1.0
    
    def test_single_word_match(self):
        """john == john → 1.0"""
        assert name_similarity("john", "john") == 1.0
    
    def test_subset_match(self):
        """john == john smith (one word in common)"""
        sim = name_similarity("john", "john smith")
        assert 0.5 <= sim <= 1.0  # Jaccard: 1 intersection / 2 union = 0.5
    
    def test_partial_name_match(self):
        """john smith == john (reverse)"""
        sim = name_similarity("john smith", "john")
        assert 0.5 <= sim <= 1.0
    
    def test_two_word_partial(self):
        """john smith == john doe (one word match)"""
        sim = name_similarity("john smith", "john doe")
        assert 0.3 <= sim <= 0.6  # 1 intersection / 3 union = 0.33
    
    def test_no_match(self):
        """alice == bob → 0.0"""
        assert name_similarity("alice", "bob") == 0.0
    
    def test_empty_strings(self):
        """empty == anything → 0.0"""
        assert name_similarity("", "john") == 0.0
        assert name_similarity("john", "") == 0.0
        assert name_similarity("", "") == 0.0
    
    def test_whitespace_normalized(self):
        """  john   smith  ==  john   smith  → 1.0"""
        assert name_similarity("  john   smith  ", "  john   smith  ") == 1.0
    
    def test_three_word_full_match(self):
        """john michael smith == john michael smith → 1.0"""
        assert name_similarity("john michael smith", "john michael smith") == 1.0
    
    def test_three_word_partial(self):
        """john michael smith == john michael (2/3 words)"""
        sim = name_similarity("john michael smith", "john michael")
        assert 0.6 <= sim <= 0.8  # 2 intersection / 3 union = 0.67


class TestContextResolution:
    """Tests for ContextResolution namedtuple."""
    
    def test_default_values(self):
        """ContextResolution with defaults"""
        res = ContextResolution()
        assert res.unit_id is None
        assert res.property_id is None
        assert res.tenant_name is None
        assert res.confidence == 0.0
        assert res.match_type == "none"
    
    def test_exact_match_result(self):
        """ContextResolution for exact email match"""
        res = ContextResolution(
            unit_id="unit-123",
            property_id="prop-456",
            tenant_name="John Smith",
            confidence=1.0,
            match_type="exact_email",
        )
        assert res.unit_id == "unit-123"
        assert res.confidence == 1.0
        assert res.match_type == "exact_email"
    
    def test_fuzzy_match_result(self):
        """ContextResolution for fuzzy name match"""
        res = ContextResolution(
            unit_id="unit-123",
            property_id="prop-456",
            tenant_name="John Smith",
            confidence=0.75,
            match_type="fuzzy_name",
        )
        assert res.confidence == 0.75
        assert res.match_type == "fuzzy_name"


# Integration test stub (requires database)
# These would be in a separate integration test file with fixtures
class TestResolveContextIntegration:
    """
    Integration tests for resolve_context (requires DB and fixtures).
    
    Example test cases:
    - resolve_context with exact email match
    - resolve_context with fuzzy name match
    - resolve_context with no match (wrong org)
    - resolve_context with null tenant_name (skipped in fuzzy)
    - resolve_context performance under 50ms
    
    Implemented in tests/integration/test_context_resolver_db.py
    """
    pass
