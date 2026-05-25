"""AI Triage Agent — classifies incoming messages.

Uses Claude Haiku for fast, cheap classification.
Returns strict JSON only — no hallucination on next steps.
Handles all urgency levels with high accuracy.
"""
import json
import time
import logging
from typing import Optional
import anthropic
from pydantic import BaseModel, Field
from backend.core.config import settings

logger = logging.getLogger(__name__)

# Emergency keywords for fallback detection
# Removed duplicate 'flooding' entry (was listed twice)
EMERGENCY_KEYWORDS = {
    "flood", "flooding", "water damage", "leaking",
    "fire", "electrical fire", "smoke",
    "gas leak", "carbon monoxide", "smell gas",
    "no heat", "frozen pipes", "temperature",
    "security breach", "break in", "break-in", "intruder",
    "sewage backup", "raw sewage",
}

TRIAGE_SYSTEM_PROMPT = """You are PropOps Triage AI. You classify property management messages with extreme accuracy.

OUTPUT ONLY VALID JSON. NO MARKDOWN. NO EXPLANATION. NO EXTRA TEXT.

Use this exact JSON schema:
{
  "category": "maintenance|billing|noise|lease|move_in|move_out|general",
  "urgency": "EMERGENCY|HIGH|MEDIUM|LOW",
  "title": "one line summary under 80 characters",
  "summary": "2-3 sentence summary of the situation",
  "sentiment": "frustrated|neutral|positive|urgent",
  "unit_mentioned": "unit number if explicitly mentioned, else null",
  "requires_vendor": true|false,
  "confidence": 0.0-1.0,
  "tags": ["array", "of", "relevant", "tags"]
}

URGENCY RULES (apply strictly):

EMERGENCY (>= 0.95 confidence):
- Flood, water damage, active leak in walls/ceiling
- Fire, smoke, electrical fire
- Gas leak, carbon monoxide detected
- No heat during winter (< 15°C outside)
- Security breach, break-in, active intruder
- Sewage backup affecting unit
- Injury or immediate medical concern in unit

HIGH (>= 0.80 confidence):
- No hot water (winter: even higher priority)
- Broken lock, door not closing properly
- Appliance failure affecting habitability (stove, fridge, heating)
- Mold growth in living spaces
- Pest infestation (rodents, bed bugs)
- Electrical hazard (exposed wiring, sparking)

MEDIUM (>= 0.60 confidence):
- Standard maintenance request (paint, caulk, fixture repair)
- Noise complaint from tenant
- Billing/payment inquiry
- Lease question (renewal, terms)
- Minor appliance malfunction

LOW (< 0.60 confidence):
- General inquiry about policies
- Feedback or compliment
- Non-urgent information request
- Administrative question

TONE GUIDANCE:
- If sender uses words like "URGENT", "EMERGENCY", "NOW", boost confidence by +0.1
- If sender is calm/polite, reduce confidence by -0.05
- Multiple punctuation marks (!!!): boost urgency by 1 level

OUTPUT CONSTRAINTS:
- Title max 80 chars — truncate if needed
- Summary exactly 2-3 sentences
- Confidence must be 0.0-1.0
- Tags array: max 5 items
- Category must match enum exactly
- Urgency must match enum exactly

FALLBACK BEHAVIOR:
If JSON parsing fails or AI response is malformed, apply keyword-based detection:
1. Check if message contains any EMERGENCY_KEYWORDS → classify as EMERGENCY
2. Otherwise default to MEDIUM with low confidence (0.3)"""


class TriageResult(BaseModel):
    """Triage classification result."""
    category: str = Field(..., description="maintenance|billing|noise|lease|move_in|move_out|general")
    urgency: str = Field(..., description="EMERGENCY|HIGH|MEDIUM|LOW")
    title: str = Field(..., description="One-line summary, max 80 chars")
    summary: str = Field(..., description="2-3 sentence summary")
    sentiment: str = Field(..., description="frustrated|neutral|positive|urgent")
    unit_mentioned: Optional[str] = Field(default=None, description="Unit number if found")
    requires_vendor: bool = Field(default=False)
    confidence: float = Field(..., ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, description="Max 5 tags")


def detect_emergency_keywords(text: str) -> bool:
    """Fallback keyword detection for urgency classification.
    
    Used when AI fails or returns malformed JSON.
    Args:
        text: Message body to check for emergency keywords
        
    Returns:
        True if any emergency keyword found (case-insensitive), False otherwise
    """
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in EMERGENCY_KEYWORDS)


async def triage_message(message_body: str, max_chars: int = 3000) -> TriageResult:
    """Classify and triage an incoming message using Claude Haiku.
    
    Args:
        message_body: Raw email/SMS text to classify
        max_chars: Maximum characters to send to AI (prevents token waste on huge messages)
        
    Returns:
        TriageResult with category, urgency, and confidence
        
    Raises:
        ValueError: If message is empty or anthropic_api_key not set
    """
    if not message_body or not message_body.strip():
        raise ValueError("Message body cannot be empty")
    
    if not settings.anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable not set")
    
    # Truncate message to avoid token waste
    truncated_body = message_body[:max_chars].strip()
    
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    
    try:
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=500,
            system=TRIAGE_SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Classify this message:\n\n{truncated_body}"
                }
            ]
        )
        
        ai_text = response.content[0].text.strip()
        
        # Parse JSON response
        try:
            data = json.loads(ai_text)
            result = TriageResult(**data)
            logger.info(f"Triage succeeded: {result.urgency} confidence={result.confidence:.2f}")
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse triage JSON: {e}\nRaw AI response: {ai_text[:200]}")
            # Fallback: keyword-based classification
            return _fallback_triage(truncated_body)
        except Exception as e:
            logger.warning(f"Triage validation error: {e}\nRaw data: {data}")
            return _fallback_triage(truncated_body)
            
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error during triage: {e}", exc_info=True)
        # Fallback: keyword-based classification
        return _fallback_triage(truncated_body)


def _fallback_triage(message_body: str) -> TriageResult:
    """Fallback triage when AI unavailable or fails.
    
    Uses keyword detection for emergency vs. medium classification.
    """
    has_emergency = detect_emergency_keywords(message_body)
    
    return TriageResult(
        category="general",
        urgency="EMERGENCY" if has_emergency else "MEDIUM",
        title="Emergency incident detected" if has_emergency else "Message pending AI review",
        summary=message_body[:150] + "..." if len(message_body) > 150 else message_body,
        sentiment="urgent",
        unit_mentioned=None,
        requires_vendor=has_emergency,
        confidence=0.95 if has_emergency else 0.3,
        tags=["fallback", "ai_unavailable"]
    )
---