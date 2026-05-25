"""Context resolution service — maps sender to tenant and unit.

Resolves email sender to property/unit context with confidence scoring.
- Exact email match: confidence=1.0
- Name fuzzy match: confidence=0.7
- No match: confidence=0.0
"""
import logging
import re
from typing import Optional, NamedTuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models.incident import Unit, Property

logger = logging.getLogger(__name__)


class ContextResolution(NamedTuple):
    """Result of context resolution lookup."""
    unit_id: Optional[str] = None
    property_id: Optional[str] = None
    tenant_name: Optional[str] = None
    confidence: float = 0.0
    match_type: str = "none"  # exact_email | fuzzy_name | none


def extract_name_from_email(email: str) -> str:
    """
    Extract name portion from email address.
    
    Examples:
        john.smith@gmail.com → john smith
        jsmith@company.com → jsmith
        john+tag@example.com → john
    
    Args:
        email: Email address to parse
        
    Returns:
        Extracted name (lowercased, normalized)
    """
    if not email or "@" not in email:
        return ""
    
    # Remove +tag suffix (e.g. john+notifications)
    local = email.split("@")[0].split("+")[0]
    
    # Replace common separators with space for matching
    # john.smith → john smith, john_smith → john smith
    name = re.sub(r"[._-]+", " ", local).strip()
    
    return name.lower()


def name_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity between two names (0.0 to 1.0).
    
    Simple approach: check if one name is substring of other or vice versa.
    More sophisticated: could use Levenshtein distance, but this is fast.
    
    Args:
        name1: First name (lowercased)
        name2: Second name (lowercased)
        
    Returns:
        Similarity score 0.0-1.0
    """
    if not name1 or not name2:
        return 0.0
    
    # Normalize whitespace
    n1 = " ".join(name1.split())
    n2 = " ".join(name2.split())
    
    # Exact match (after normalization)
    if n1 == n2:
        return 1.0
    
    # Check if one is substring of other (handles "john" vs "john smith")
    words1 = set(n1.split())
    words2 = set(n2.split())
    
    if not words1 or not words2:
        return 0.0
    
    # Jaccard similarity: intersection / union
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


async def resolve_context(
    db: AsyncSession,
    org_id: str,
    sender_email: str,
    fuzzy_match_threshold: float = 0.7,
) -> ContextResolution:
    """
    Resolve sender email to property/unit context.
    
    Strategy:
    1. Try exact email match (fastest, highest confidence)
    2. Try fuzzy name match against tenant_name (slower, medium confidence)
    3. Return no match if neither succeeds
    
    Args:
        db: Async database session
        org_id: Organization UUID to scope search
        sender_email: Sender email address
        fuzzy_match_threshold: Minimum similarity (0.0-1.0) for fuzzy match
        
    Returns:
        ContextResolution with unit_id, property_id, confidence
        
    Performance:
        - Exact match: O(1) index lookup ~1-5ms
        - Fuzzy match: O(n) scan of tenant_name, typically <50ms for <1000 units
    """
    sender_lower = sender_email.lower().strip()
    
    # Step 1: Exact email match
    # SECURITY-REVIEW: sender_email is from untrusted source, but query is parameterized
    exact_query = (
        select(Unit)
        .join(Property, Unit.property_id == Property.id)
        .where(
            Property.org_id == org_id,
            func.lower(Unit.tenant_email) == sender_lower,
        )
        .limit(1)
    )
    exact_result = await db.execute(exact_query)
    exact_unit = exact_result.scalar_one_or_none()
    
    if exact_unit:
        logger.info(
            f"context_resolver: exact match {sender_email} → "
            f"unit {exact_unit.id} property {exact_unit.property_id}"
        )
        return ContextResolution(
            unit_id=str(exact_unit.id),
            property_id=str(exact_unit.property_id),
            tenant_name=exact_unit.tenant_name,
            confidence=1.0,
            match_type="exact_email",
        )
    
    # Step 2: Fuzzy name match
    sender_name = extract_name_from_email(sender_lower)
    if not sender_name:
        logger.debug(f"context_resolver: could not extract name from {sender_email}")
        return ContextResolution(confidence=0.0, match_type="none")
    
    # Fetch all units for this org with tenant names
    # AMBIGUITY: if multiple fuzzy matches exist, we pick the first (highest similarity)
    # Consider: should we return all candidates for manual review? For now, first best match.
    fuzzy_query = (
        select(Unit)
        .join(Property, Unit.property_id == Property.id)
        .where(
            Property.org_id == org_id,
            Unit.tenant_name.isnot(None),
        )
    )
    fuzzy_result = await db.execute(fuzzy_query)
    candidate_units = fuzzy_result.scalars().all()
    
    best_match: Optional[Unit] = None
    best_similarity: float = 0.0
    
    for unit in candidate_units:
        if not unit.tenant_name:
            continue
        
        tenant_name_normalized = unit.tenant_name.lower()
        similarity = name_similarity(sender_name, tenant_name_normalized)
        
        if similarity > best_similarity and similarity >= fuzzy_match_threshold:
            best_similarity = similarity
            best_match = unit
    
    if best_match:
        logger.info(
            f"context_resolver: fuzzy match {sender_email} ({sender_name}) → "
            f"unit {best_match.id} tenant {best_match.tenant_name} (similarity={best_similarity:.2f})"
        )
        return ContextResolution(
            unit_id=str(best_match.id),
            property_id=str(best_match.property_id),
            tenant_name=best_match.tenant_name,
            confidence=best_similarity,
            match_type="fuzzy_name",
        )
    
    # Step 3: No match
    logger.debug(
        f"context_resolver: no match for {sender_email} "
        f"({sender_name}) in org {org_id}"
    )
    return ContextResolution(confidence=0.0, match_type="none")
---