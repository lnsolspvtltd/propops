"""AI Triage Agent — classifies incoming messages.

Uses Claude Haiku for fast, cheap classification.
Returns strict JSON only — no hallucination on next steps.
"""
import json
import time
import logging
from typing import Optional
import anthropic
from pydantic import BaseModel
from backend.core.config import settings

logger = logging.getLogger(__name__)

TRIAGE_SYSTEM_PROMPT = """You are PropOps Triage AI. You classify property management messages.

Output ONLY valid JSON. No explanation. No markdown. No extra text.

JSON schema:
{
  "category": "maintenance|billing|noise|lease|move_in|move_out|general",
  "urgency": "EMERGENCY|HIGH|MEDIUM|LOW",
  "title": "one line summary under 80 chars",
  "summary": "2-3 sentence summary of the situation",
  "sentiment": "frustrated|neutral|positive|urgent",
  "unit_mentioned": "unit number if mentioned, else null",
  "requires_vendor": true|false,
  "confidence": 0.0-1.0,
  "tags": ["array", "of", "relevant", "tags"]
}

Urgency rules:
- EMERGENCY: flood, fire, gas leak, no heat in winter, security breach
- HIGH: no hot water, broken lock, appliance failure affecting habitability
- MEDIUM: maintenance request, noise complaint, billing question
- LOW: general inquiry, feedback, non-urgent request"""


class TriageResult(BaseModel):
    category: str
    urgency: str
    title: str
    summary: str
    sentiment: str
    unit_mentioned: Optional[str] = None
    requires_vendor: bool = False
    confidence: float
    tags: list[str] = []
    model_used: str = ""
    success: bool = True
    error: Optional[str] = None


def triage_message(
    message_body: str,
    sender: str = "",
    subject: str = "",
) -> TriageResult:
    """
    Classify an incoming message using Claude Haiku.

    Args:
        message_body: Full message text
        sender: Sender email/phone
        subject: Email subject if available

    Returns:
        TriageResult with classification
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    prompt = f"""Classify this property management message:

SENDER: {sender}
SUBJECT: {subject}
MESSAGE:
{message_body[:2000]}"""

    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=512,
                system=TRIAGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            data = json.loads(raw)
            return TriageResult(
                **data,
                model_used="claude-haiku-4-5",
                success=True,
            )
        except json.JSONDecodeError as e:
            logger.warning(f"triage: JSON parse error attempt {attempt+1}: {e}")
            if attempt == 2:
                return TriageResult(
                    category="general", urgency="MEDIUM",
                    title="Message requires manual review",
                    summary=message_body[:200],
                    sentiment="neutral", confidence=0.0,
                    success=False, error=f"JSON parse failed: {e}",
                )
        except anthropic.RateLimitError:
            time.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"triage: error attempt {attempt+1}: {e}")
            if attempt == 2:
                return TriageResult(
                    category="general", urgency="MEDIUM",
                    title="Triage failed — manual review required",
                    summary=message_body[:200],
                    sentiment="neutral", confidence=0.0,
                    success=False, error=str(e),
                )
    return TriageResult(
        category="general", urgency="MEDIUM",
        title="Triage failed", summary="",
        sentiment="neutral", confidence=0.0,
        success=False, error="Max retries exceeded",
    )