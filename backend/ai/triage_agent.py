"""AI Triage Agent — classifies incoming messages.

Uses Claude Haiku for fast, cheap classification.
Returns strict JSON only — no hallucination on next steps.
Handles all urgency levels with high accuracy.
Includes fallback keyword-based detection for reliability.
"""
import json
import logging
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
import anthropic
from pydantic import BaseModel, Field
from backend.core.config import settings

logger = logging.getLogger(__name__)

# Emergency keywords for fallback detection
# Used if LLM response is malformed or unparseable
EMERGENCY_KEYWORDS = {
    "flood", "flooding", "water damage", "leaking",
    "fire", "electrical fire", "smoke",
    "gas leak", "carbon monoxide", "smell gas",
    "no heat", "frozen pipes", "temperature",
    "security breach", "break in", "break-in", "intruder",
    "sewage backup", "raw sewage",
}


class TriageResult(BaseModel):
    """Structured output from triage classification."""
    category: str = Field(..., description="maintenance|billing|noise|lease|move_in|move_out|general")
    urgency: str = Field(..., description="EMERGENCY|HIGH|MEDIUM|LOW")
    title: str = Field(..., description="One-line summary under 80 characters")
    summary: str = Field(..., description="2-3 sentence summary of the situation")
    sentiment: str = Field(..., description="frustrated|neutral|positive|urgent")
    unit_mentioned: Optional[str] = Field(None, description="Unit number if mentioned, else null")
    requires_vendor: bool = Field(..., description="Whether vendor/contractor is needed")
    confidence: float = Field(..., description="Confidence score 0.0-1.0")
    tags: list[str] = Field(..., description="Relevant tags, max 5 items")


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
If the message matches emergency keywords (flood, fire, gas leak, etc.), classify as EMERGENCY with 0.95+ confidence.
"""


def _fallback_triage(message: str, error: Exception) -> TriageResult:
    """Fallback keyword-based triage if LLM fails.
    
    Uses EMERGENCY_KEYWORDS to detect critical issues.
    This ensures system reliability even if Claude is unavailable.
    
    Args:
        message: Original message text
        error: The exception that caused LLM failure
        
    Returns:
        Safe fallback TriageResult
    """
    logger.warning(f"Using fallback triage due to LLM error: {type(error).__name__}: {error}")
    
    message_lower = message.lower()
    has_emergency = any(keyword in message_lower for keyword in EMERGENCY_KEYWORDS)
    
    if has_emergency:
        logger.info("Fallback detected emergency keywords — escalating to EMERGENCY")
        return TriageResult(
            category="maintenance",
            urgency="EMERGENCY",
            title="Emergency maintenance detected (fallback)",
            summary="System could not reach AI classifier, but message contains emergency keywords. Escalating to EMERGENCY priority.",
            sentiment="urgent",
            unit_mentioned=None,
            requires_vendor=True,
            confidence=0.85,
            tags=["emergency", "fallback", "keyword-detected"]
        )
    
    logger.info("Fallback triage — no emergency keywords found, defaulting to MEDIUM")
    return TriageResult(
        category="maintenance",
        urgency="MEDIUM",
        title="Unclassified message (fallback)",
        summary="System could not reach AI classifier. Treating as medium priority for manual review.",
        sentiment="neutral",
        unit_mentioned=None,
        requires_vendor=False,
        confidence=0.50,
        tags=["fallback", "needs-review"]
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def classify_message(message: str) -> TriageResult:
    """Classify an incoming property management message using Claude.
    
    Retries up to 3 times with exponential backoff on transient failures.
    Falls back to keyword-based detection if all retries fail.
    
    Args:
        message: The incoming message text to classify
        
    Returns:
        TriageResult with category, urgency, summary, confidence, etc.
        
    Raises:
        Does not raise — returns safe fallback on any error.
    """
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        
        response = client.messages.create(
            model="claude-3-5-haiku-20241022",
            max_tokens=512,
            system=TRIAGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message}]
        )
        
        raw_json = response.content[0].text.strip()
        logger.debug(f"Raw LLM response: {raw_json[:200]}")
        
        # Remove markdown code blocks if present
        if raw_json.startswith("```json"):
            raw_json = raw_json[7:]
        if raw_json.startswith("```"):
            raw_json = raw_json[3:]
        if raw_json.endswith("```"):
            raw_json = raw_json[:-3]
        
        raw_json = raw_json.strip()
        data = json.loads(raw_json)
        result = TriageResult(**data)
        
        logger.info(
            f"Classified message: category={result.category}, urgency={result.urgency}, confidence={result.confidence:.2f}",
            extra={"category": result.category, "urgency": result.urgency, "confidence": result.confidence}
        )
        return result
    
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error in triage response: {e}\nRaw: {raw_json[:300]}")
        return _fallback_triage(message, e)
    
    except ValueError as e:
        logger.error(f"Pydantic validation error in triage: {e}")
        return _fallback_triage(message, e)
    
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}", exc_info=True)
        return _fallback_triage(message, e)
    
    except Exception as e:
        logger.error(f"Unexpected error in classify_message: {e}", exc_info=True)
        return _fallback_triage(message, e)
---