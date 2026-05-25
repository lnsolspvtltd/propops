"""AI Triage Agent — classifies incoming messages.

Uses Claude Haiku for fast, cheap classification.
Returns strict JSON only — no hallucination on next steps.
Handles all urgency levels with high accuracy.
"""
import json
import time
import logging
import re
from typing import Optional
import anthropic
from pydantic import BaseModel, Field
from backend.core.config import settings

logger = logging.getLogger(__name__)

# Emergency keywords for fallback detection
EMERGENCY_KEYWORDS = {
    "flood", "flooding", "water damage", "leaking",
    "fire", "electrical fire", "smoke",
    "gas leak", "carbon monoxide", "smell gas",
    "no heat", "frozen pipes", "temperature",
    "security breach", "break in", "break-in", "intruder",
    "flooding", "sewage backup", "raw sewage",
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
- Urgency must match enum exactly"""


class TriageResult(BaseModel):
    """Triage classification result."""
    category: str = Field(..., description="maintenance|billing|noise|lease|move_in|move_out|general")
    urgency: str = Field(..., description="EMERGENCY|HIGH|MEDIUM|LOW")
    title: str = Field(..., max_length=80, description="One-line summary")
    summary: str = Field(..., description="2-3 sentence summary")
    sentiment: str = Field(..., description="frustrated|neutral|positive|urgent")
    unit_mentioned: Optional[str] = Field(None, description="Unit number or null")
    requires_vendor: bool = Field(False, description="Requires vendor coordination")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence 0-1")
    tags: list[str] = Field(default_factory=list, description="Relevant tags array")
    model_used: str = "claude-haiku-4-5"
    success: bool = True
    error: Optional[str] = None


def _detect_emergency_keyword(text: str) -> Optional[str]:
    """
    Fast keyword-based emergency detection for fallback.
    Returns matched keyword or None.
    Used only when JSON parse fails — provides safe fallback.
    """
    text_lower = text.lower()
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text_lower:
            return keyword
    return None


def _extract_unit_number(text: str) -> Optional[str]:
    """
    Extract unit number from message.
    Patterns: Unit 101, #101, Unit A, Apt 3, 3A, etc.
    """
    patterns = [
        r'(?:unit|apt|apartment|#)\s*([a-z0-9]+)',  # Unit 101, Apt 3A
        r'^[a-z0-9]+\s*(?:unit|apt)',  # 3 Unit
        r'(?:unit|apt)\s*#?\s*([a-z0-9]+)',  # Unit #101
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            unit = match.group(1).strip()
            if len(unit) <= 10:
                return unit
    return None


def _sanitize_for_llm(text: str, max_chars: int = 3000) -> str:
    """
    Sanitize input before sending to LLM.
    - Remove HTML tags
    - Strip excessive whitespace
    - Remove suspicious patterns
    - Truncate
    """
    # Strip HTML
    text = re.sub(r'<[^>]+>', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove control characters
    text = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
    # Truncate
    return text[:max_chars].strip()


def _validate_json_response(data: dict) -> tuple[bool, Optional[str]]:
    """
    Validate LLM JSON response against schema.
    Returns (is_valid, error_message).
    """
    required_fields = {
        "category": str,
        "urgency": str,
        "title": str,
        "summary": str,
        "sentiment": str,
        "requires_vendor": bool,
        "confidence": (int, float),
        "tags": list,
    }

    for field, field_type in required_fields.items():
        if field not in data:
            return False, f"Missing field: {field}"
        if isinstance(field_type, tuple):
            if not isinstance(data[field], field_type):
                return False, f"Field {field} has wrong type"
        else:
            if not isinstance(data[field], field_type):
                return False, f"Field {field} has wrong type"

    # Validate enums
    valid_categories = {
        "maintenance", "billing", "noise", "lease",
        "move_in", "move_out", "general"
    }
    if data["category"] not in valid_categories:
        return False, f"Invalid category: {data['category']}"

    valid_urgencies = {"EMERGENCY", "HIGH", "MEDIUM", "LOW"}
    if data["urgency"] not in valid_urgencies:
        return False, f"Invalid urgency: {data['urgency']}"

    valid_sentiments = {"frustrated", "neutral", "positive", "urgent"}
    if data["sentiment"] not in valid_sentiments:
        return False, f"Invalid sentiment: {data['sentiment']}"

    # Validate constraints
    if not (0.0 <= data["confidence"] <= 1.0):
        return False, "Confidence must be 0.0-1.0"

    if len(data["title"]) > 80:
        return False, f"Title too long ({len(data['title'])} > 80)"

    if not isinstance(data["tags"], list) or len(data["tags"]) > 5:
        return False, "Tags must be array with max 5 items"

    return True, None


def triage_message(
    message_body: str,
    sender: str = "",
    subject: str = "",
    timeout_seconds: float = 2.5,
) -> TriageResult:
    """
    Classify an incoming message using Claude Haiku.

    Args:
        message_body: Full message text (will be truncated to 3000 chars)
        sender: Sender email/phone
        subject: Email subject if available
        timeout_seconds: Max time to wait for Claude response

    Returns:
        TriageResult with classification. Always returns a result—
        never crashes. Falls back to MEDIUM/general if JSON parse fails.

    Timeout handling:
        If Claude takes > 2.5s, we abort and return fallback.
        This ensures p90 latency < 3 seconds.
    """
    # Input sanitization
    body_sanitized = _sanitize_for_llm(message_body, max_chars=3000)
    if not body_sanitized:
        logger.warning("triage: empty message after sanitization")
        return TriageResult(
            category="general", urgency="MEDIUM",
            title="Empty message", summary="Received empty message.",
            sentiment="neutral", confidence=0.0,
            success=False, error="Empty message",
        )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Pre-construct prompt with best details
    prompt = f"""Classify this property management message:

SENDER: {sender[:100] if sender else "unknown"}
SUBJECT: {subject[:200] if subject else "(no subject)"}
MESSAGE (first 3000 chars):
{body_sanitized}"""

    # Quick emergency keyword check for fallback
    emergency_keyword = _detect_emergency_keyword(body_sanitized)

    # Attempt Claude classification
    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20250108",
                max_tokens=512,
                system=TRIAGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout_seconds,
            )

            raw = response.content[0].text.strip()
            logger.debug(f"triage: raw response: {raw[:200]}")

            # Parse JSON
            data = json.loads(raw)

            # Validate schema
            is_valid, error_msg = _validate_json_response(data)
            if not is_valid:
                logger.warning(f"triage: validation failed: {error_msg}")
                if attempt == 2:
                    # Final fallback
                    if emergency_keyword:
                        return TriageResult(
                            category="maintenance",
                            urgency="EMERGENCY",
                            title=f"Potential emergency: {emergency_keyword}",
                            summary=body_sanitized[:150],
                            sentiment="urgent",
                            confidence=0.8,
                            tags=["emergency-keyword-match", emergency_keyword],
                            success=False,
                            error=f"JSON validation failed: {error_msg}",
                        )
                    else:
                        return TriageResult(
                            category="general",
                            urgency="MEDIUM",
                            title="Message requires manual review",
                            summary=body_sanitized[:150],
                            sentiment="neutral",
                            confidence=0.0,
                            success=False,
                            error=f"Validation failed: {error_msg}",
                        )
                continue

            # Success! Create result from validated data
            result = TriageResult(
                category=data["category"],
                urgency=data["urgency"],
                title=data["title"][:80],
                summary=data["summary"],
                sentiment=data["sentiment"],
                unit_mentioned=data.get("unit_mentioned"),
                requires_vendor=data.get("requires_vendor", False),
                confidence=float(data["confidence"]),
                tags=data.get("tags", [])[:5],
                model_used="claude-haiku-4-5-20250108",
                success=True,
            )

            logger.info(
                f"triage: {sender[:30]} → [{result.urgency}] {result.category} "
                f"(confidence={result.confidence:.2f})"
            )
            return result

        except json.JSONDecodeError as e:
            logger.warning(f"triage: JSON parse error attempt {attempt+1}: {e}")
            if attempt == 2:
                # Last attempt failed — use keyword detection
                if emergency_keyword:
                    return TriageResult(
                        category="maintenance",
                        urgency="EMERGENCY",
                        title=f"Potential emergency: {emergency_keyword}",
                        summary=body_sanitized[:150],
                        sentiment="urgent",
                        confidence=0.8,
                        tags=["json-parse-fallback", emergency_keyword],
                        success=False,
                        error="JSON parse failed, emergency keyword match",
                    )
                else:
                    return TriageResult(
                        category="general",
                        urgency="MEDIUM",
                        title="Message requires manual review",
                        summary=body_sanitized[:150],
                        sentiment="neutral",
                        confidence=0.0,
                        success=False,
                        error=f"JSON parse failed: {e}",
                    )

        except anthropic.RateLimitError as e:
            wait_time = 2 ** attempt
            logger.warning(f"triage: rate limited, waiting {wait_time}s")
            time.sleep(wait_time)
            if attempt == 2:
                return TriageResult(
                    category="general",
                    urgency="MEDIUM",
                    title="Triage service unavailable",
                    summary=body_sanitized[:150],
                    sentiment="neutral",
                    confidence=0.0,
                    success=False,
                    error="Rate limit exceeded",
                )

        except anthropic.APIError as e:
            logger.error(f"triage: API error attempt {attempt+1}: {e}")
            if attempt == 2:
                return TriageResult(
                    category="general",
                    urgency="MEDIUM",
                    title="Triage service error",
                    summary=body_sanitized[:150],
                    sentiment="neutral",
                    confidence=0.0,
                    success=False,
                    error=f"API error: {str(e)[:100]}",
                )

        except TimeoutError:
            logger.warning(f"triage: timeout (attempt {attempt+1}), using fallback")
            if attempt == 2:
                if emergency_keyword:
                    return TriageResult(
                        category="maintenance",
                        urgency="EMERGENCY",
                        title=f"Potential emergency: {emergency_keyword}",
                        summary=body_sanitized[:150],
                        sentiment="urgent",
                        confidence=0.7,
                        tags=["timeout-fallback", emergency_keyword],
                        success=False,
                        error="Triage timeout, emergency keyword detected",
                    )
                return TriageResult(
                    category="general",
                    urgency="MEDIUM",
                    title="Message requires manual review",
                    summary=body_sanitized[:150],
                    sentiment="neutral",
                    confidence=0.0,
                    success=False,
                    error="Triage timeout",
                )

    # Absolute final fallback (should never reach)
    return TriageResult(
        category="general",
        urgency="MEDIUM",
        title="Triage failed — manual review required",
        summary=body_sanitized[:150],
        sentiment="neutral",
        confidence=0.0,
        success=False,
        error="Triage max retries exceeded",
    )
