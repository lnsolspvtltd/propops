"""AI Draft Generation Agent.

Uses Claude Sonnet to write professional, context-aware replies.
SAFETY: NEVER admits liability or fault on behalf of the property manager.
SAFETY: NEVER confirms payment amounts, deposits, or financial figures.
SAFETY: NEVER confirms a specific appointment time.
Always be professional, empathetic, solution-focused.
"""
import time
import logging
import re
from typing import Optional
import anthropic
from pydantic import BaseModel, ConfigDict
from backend.core.config import settings

logger = logging.getLogger(__name__)

# SAFETY-REVIEW: Liability and financial confirmation patterns to explicitly forbid
LIABILITY_PATTERNS = [
    r"we\s+(?:accept|accept\s+responsibility|admit|admit\s+fault|are\s+liable|are\s+responsible)",
    r"(?:our|we)\s+fault",
    r"(?:our|we)\s+mistake",
    r"(?:our|we)\s+error",
]

FINANCIAL_CONFIRMATION_PATTERNS = [
    r"confirm(?:ed)?\s+(?:the\s+)?(?:payment|amount|deposit|fee|charge|rent)",
    r"(?:payment|amount|deposit|fee|charge|rent)\s+(?:of\s+)?\$?\d+",
    r"(?:payment|deposit)\s+(?:received|confirmed|processed)",
]

TIME_CONFIRMATION_PATTERNS = [
    r"we\s+will\s+(?:arrive|come|visit)\s+(?:on|at)\s+\d+:\d+",
    r"(?:appointment|visit|arrival)\s+(?:scheduled|confirmed|set)\s+(?:for|at)\s+\d+:\d+",
    r"see\s+you\s+(?:on|at)\s+\d+:\d+",
]

DRAFT_SYSTEM_PROMPTS = {
    "tenant_reply": """You are PropOps Draft AI, writing professional responses to tenants on behalf of a property management company.

ABSOLUTE SAFETY RULES:
- NEVER admit liability, fault, or responsibility
- NEVER confirm payment amounts, deposits, or financial figures
- NEVER confirm a specific appointment time (say "we will be in touch to confirm a time that works for you")
- NEVER promise a timeline you cannot guarantee
- NEVER say "we are sorry" or apologize on behalf of the company
- If tenant has a legitimate grievance, acknowledge their concern without admitting fault

TONE GUIDELINES:
- Professional, empathetic, and solution-focused
- Acknowledge the tenant's concern (validation, not admission)
- Provide next steps or timeline for resolution
- Be clear and concise (under 200 words)
- Use the tenant's name if known

EXAMPLE SAFE RESPONSES:
❌ "We apologize for the noise. This is our maintenance crew's fault."
✅ "Thank you for reporting the noise issue. We understand how disruptive this is. We will investigate and follow up with you within 24 hours."

❌ "We confirm your deposit of $2,000 has been received."
✅ "We acknowledge receipt of your security deposit. Our accounting team will send you a confirmation email within 2 business days."

❌ "Our technician will arrive tomorrow at 2 PM."
✅ "We will be in touch to confirm a time that works for both you and our maintenance team."

Write the reply body only. Do NOT include greeting like "Dear [Name]" or closing like "Regards". That will be added separately.""",

    "vendor_outreach": """You are PropOps Draft AI, writing professional outreach emails to contractors/vendors on behalf of a property management company.

ABSOLUTE SAFETY RULES:
- NEVER confirm any tenant complaint as fact
- NEVER admit liability for damage or defects
- NEVER confirm budget or payment terms in draft (use "per your estimate" or "as discussed")
- Keep professional and courteous tone
- Frame as inquiry, not accusation

TONE GUIDELINES:
- Professional and collaborative
- Reference specific issue without assigning blame
- Request quote or timeline
- Keep under 200 words

EXAMPLE SAFE RESPONSES:
❌ "The tenant's toilet is broken because our building is poorly maintained."
✅ "We have a request for plumbing service at Unit 4B. Could you provide a quote for inspection and repair?"

Write the reply body only. Do NOT include greeting or closing.""",

    "escalation": """You are PropOps Draft AI, writing escalation notices to property owners.

ABSOLUTE SAFETY RULES:
- State facts only — no speculation or blame
- Separate incident description from property manager's actions
- Be clear and direct about urgency level
- Use professional, neutral tone

TONE GUIDELINES:
- Factual and urgent (if EMERGENCY/HIGH)
- Clear summary of issue
- Explicit next steps and timeline
- Keep under 300 words (escalations can be longer)

Write the body only. Do NOT include greeting or closing.""",
}


class DraftResult(BaseModel):
    """Result of draft generation attempt."""
    model_config = ConfigDict(from_attributes=True)
    
    subject: str
    body: str
    draft_type: str
    model_used: str = ""
    success: bool = True
    error: Optional[str] = None
    safety_checked: bool = False


def _sanitize_for_safety(text: str) -> str:
    """
    Remove or flag text that violates safety rules.
    Operates as a post-generation safety net (not primary defense).
    
    SECURITY-REVIEW: This is a secondary check. Primary defense is system prompt.
    If this function modifies output, we log and surface to human.
    """
    original = text
    
    # Flag liability admissions
    for pattern in LIABILITY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"draft_agent: LIABILITY pattern detected: {pattern}")
            # Replace with safe alternative
            text = re.sub(pattern, "[REMOVED: liability admission]", text, flags=re.IGNORECASE)
    
    # Flag financial confirmations
    for pattern in FINANCIAL_CONFIRMATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"draft_agent: FINANCIAL_CONFIRMATION pattern detected: {pattern}")
            text = re.sub(
                pattern,
                "[REMOVED: financial confirmation]",
                text,
                flags=re.IGNORECASE
            )
    
    # Flag time confirmations
    for pattern in TIME_CONFIRMATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"draft_agent: TIME_CONFIRMATION pattern detected: {pattern}")
            text = re.sub(
                pattern,
                "[REMOVED: time confirmation]",
                text,
                flags=re.IGNORECASE
            )
    
    if text != original:
        logger.error(f"draft_agent: Safety check modified output. Original:\n{original}\n\nModified:\n{text}")
        return text  # Return modified, but flagged
    
    return text


def _generate_subject_line(incident_title: str, urgency: str, draft_type: str) -> str:
    """Generate appropriate subject line based on draft type and urgency."""
    if draft_type == "escalation":
        prefix = "ESCALATION:" if urgency in ["EMERGENCY", "HIGH"] else "Alert:"
        return f"{prefix} {incident_title}"
    elif draft_type == "vendor_outreach":
        return f"Service Request: {incident_title}"
    elif urgency == "EMERGENCY":
        return f"URGENT: {incident_title}"
    else:
        return f"Re: {incident_title}"


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
        category: Incident category (maintenance|billing|noise|lease|other)
        urgency: EMERGENCY|HIGH|MEDIUM|LOW
        tenant_name: Tenant/sender's name for personalisation
        property_name: Property name
        draft_type: tenant_reply | vendor_outreach | escalation

    Returns:
        DraftResult with subject, body, and safety_checked flag

    Raises:
        ValueError: If draft_type is invalid or required fields missing
    """
    if draft_type not in DRAFT_SYSTEM_PROMPTS:
        raise ValueError(f"Invalid draft_type: {draft_type}. Must be one of {list(DRAFT_SYSTEM_PROMPTS.keys())}")

    if not incident_title or not incident_summary:
        raise ValueError("incident_title and incident_summary are required")

    if not settings.anthropic_api_key:
        logger.error("draft_agent: ANTHROPIC_API_KEY not configured")
        raise ValueError("Anthropic API key not configured")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Map urgency to tone guidance
    urgency_guidance = {
        "EMERGENCY": "This is CRITICAL. Express immediate concern and swift action.",
        "HIGH": "This is high priority. Respond with urgency and clear next steps.",
        "MEDIUM": "Standard priority. Professional, helpful, and responsive tone.",
        "LOW": "Low priority. Friendly and informative; no rush needed.",
    }.get(urgency, "Professional and helpful tone.")

    # Build context for draft
    context_parts = [
        f"INCIDENT: {incident_title}",
        f"SUMMARY: {incident_summary}",
        f"CATEGORY: {category}",
        f"URGENCY: {urgency}",
    ]
    if tenant_name:
        context_parts.append(f"SENDER/RECIPIENT: {tenant_name}")
    if property_name:
        context_parts.append(f"PROPERTY: {property_name}")
    context_parts.append(f"DRAFT TYPE: {draft_type}")
    context_parts.append(f"TONE: {urgency_guidance}")

    prompt = f"""Generate a professional property management response:

{chr(10).join(context_parts)}

Requirements:
- Acknowledge the situation without admitting fault
- Provide next steps or timeline
- Be professional, empathetic, solution-focused
- Keep under 200 words (unless escalation, then up to 300)
- No greeting or closing (they are added separately)"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5-20251022",
                max_tokens=1024,
                system=DRAFT_SYSTEM_PROMPTS[draft_type],
                messages=[{"role": "user", "content": prompt}],
            )

            body = response.content[0].text.strip()

            # SECURITY-REVIEW: Post-generation safety check
            body = _sanitize_for_safety(body)

            subject = _generate_subject_line(incident_title, urgency, draft_type)

            logger.info(
                f"draft_agent: generated {draft_type} draft for '{incident_title}' "
                f"[{urgency}] (attempt {attempt + 1}, model={response.model})"
            )

            return DraftResult(
                subject=subject,
                body=body,
                draft_type=draft_type,
                model_used=response.model,
                success=True,
                safety_checked=True,
            )

        except anthropic.RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # exponential backoff: 1s, 2s, 4s
                logger.warning(f"draft_agent: rate limited, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                logger.error(f"draft_agent: rate limit exceeded after {max_retries} attempts")
                return DraftResult(
                    subject=_generate_subject_line(incident_title, urgency, draft_type),
                    body="We have received your request and will respond shortly with more information.",
                    draft_type=draft_type,
                    success=False,
                    error="Rate limit exceeded — using fallback response",
                    safety_checked=True,
                )

        except anthropic.APIError as e:
            logger.error(f"draft_agent: API error attempt {attempt + 1}/{max_retries}: {e}")
            if attempt == max_retries - 1:
                # Return safe fallback on final failure
                fallback_messages = {
                    "tenant_reply": "Thank you for reaching out. We have received your message and will respond promptly.",
                    "vendor_outreach": "We are reaching out regarding a service request. Please let us know your availability.",
                    "escalation": "We are notifying you of an issue that requires your attention. Details are below.",
                }
                return DraftResult(
                    subject=_generate_subject_line(incident_title, urgency, draft_type),
                    body=fallback_messages.get(draft_type, "We will be in touch shortly."),
                    draft_type=draft_type,
                    success=False,
                    error=f"API error: {str(e)[:100]}",
                    safety_checked=True,
                )

        except Exception as e:
            logger.error(f"draft_agent: unexpected error attempt {attempt + 1}/{max_retries}: {type(e).__name__}: {e}")
            if attempt == max_retries - 1:
                return DraftResult(
                    subject=_generate_subject_line(incident_title, urgency, draft_type),
                    body="We will respond to your message as soon as possible.",
                    draft_type=draft_type,
                    success=False,
                    error=f"Internal error: {type(e).__name__}",
                    safety_checked=True,
                )

    # Should not reach here, but safety net
    return DraftResult(
        subject="",
        body="",
        draft_type=draft_type,
        success=False,
        error="Unknown error in draft generation",
        safety_checked=False,
    )