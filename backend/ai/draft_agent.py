"""AI Draft Generation Agent.

Uses Claude Sonnet to write professional, context-aware replies.
NEVER admits liability. NEVER confirms financials. NEVER autonomous scheduling.
"""
import time
import logging
from typing import Optional
import anthropic
from pydantic import BaseModel
from backend.core.config import settings

logger = logging.getLogger(__name__)

DRAFT_SYSTEM_PROMPT = """You are PropOps Draft AI writing on behalf of a property management company.

ABSOLUTE RULES:
- NEVER admit liability or fault
- NEVER confirm payment amounts, deposits, or financials
- NEVER confirm a specific appointment time (say "we will be in touch to confirm")
- NEVER promise a timeline you cannot guarantee
- Always be professional, empathetic, and solution-focused
- Keep replies under 200 words unless the situation demands more

Write the reply body only. No subject line. No greeting like "Dear [Name]" — that is added separately."""


class DraftResult(BaseModel):
    subject: str
    body: str
    draft_type: str
    model_used: str = ""
    success: bool = True
    error: Optional[str] = None


def generate_draft(
    incident_title: str,
    incident_summary: str,
    category: str,
    urgency: str,
    tenant_name: str = "",
    property_name: str = "",
    draft_type: str = "tenant_reply",
) -> DraftResult:
    """
    Generate a professional reply draft using Claude Sonnet.

    Args:
        incident_title: One-line incident description
        incident_summary: AI summary of the situation
        category: Incident category
        urgency: EMERGENCY|HIGH|MEDIUM|LOW
        tenant_name: Tenant's name for personalisation
        property_name: Property name
        draft_type: tenant_reply | vendor_outreach | escalation

    Returns:
        DraftResult with subject and body
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    urgency_guidance = {
        "EMERGENCY": "This is an EMERGENCY. Express immediate concern and action.",
        "HIGH": "This is high priority. Respond with urgency and clear next steps.",
        "MEDIUM": "Standard priority. Professional and helpful tone.",
        "LOW": "Low priority. Friendly and informative.",
    }.get(urgency, "Professional tone.")

    prompt = f"""Write a property management reply for this incident:

INCIDENT: {incident_title}
SUMMARY: {incident_summary}
CATEGORY: {category}
URGENCY: {urgency}
TENANT: {tenant_name or "Resident"}
PROPERTY: {property_name or "your property"}
DRAFT TYPE: {draft_type}
TONE GUIDANCE: {urgency_guidance}

Write the reply body. Start with acknowledging the issue."""

    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20251001",
                max_tokens=1024,
                system=DRAFT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            body = response.content[0].text.strip()
            subject = f"Re: {incident_title}"
            if urgency == "EMERGENCY":
                subject = f"URGENT: {incident_title}"

            return DraftResult(
                subject=subject, body=body,
                draft_type=draft_type,
                model_used="claude-sonnet-4-5-20251001",
                success=True,
            )
        except anthropic.RateLimitError:
            time.sleep(2 ** attempt)
        except Exception as e:
            logger.error(f"draft_agent: error attempt {attempt+1}: {e}")
            if attempt == 2:
                return DraftResult(
                    subject=f"Re: {incident_title}",
                    body="Thank you for reaching out. We have received your message and will respond shortly.",
                    draft_type=draft_type,
                    success=False, error=str(e),
                )
    return DraftResult(
        subject="", body="", draft_type=draft_type,
        success=False, error="Max retries exceeded",
    )
