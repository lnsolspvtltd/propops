"""AI Draft Generation Agent.

Uses Claude Sonnet to write professional, context-aware replies.
SAFETY: NEVER admits liability or fault on behalf of the property manager.
SAFETY: NEVER confirms payment amounts, deposits, or financial figures.
SAFETY: NEVER confirms a specific appointment time.
Always be professional, empathetic, solution-focused.
"""
import logging
import re
from typing import Optional
import anthropic
from pydantic import BaseModel, ConfigDict
from backend.core.config import settings

logger = logging.getLogger(__name__)

# SECURITY-REVIEW: Liability and financial confirmation patterns to explicitly forbid
# These patterns are checked both pre- and post-generation to prevent unsafe output
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
- NEVER admit liability, fault, or responsibility for any issue
- NEVER confirm payment amounts, deposits, or financial figures by number
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

    "vendor_outreach": """You are PropOps Draft AI, writing professional outreach emails to contractors and vendors on behalf of a property management company.

TONE GUIDELINES:
- Professional, clear, and direct
- Lead with the property issue and urgency level
- Provide specific details (address, unit number, issue description)
- Include contact person and preferred communication method
- Be concise (under 150 words)

CONTENT REQUIREMENTS:
- Property name and address
- Unit number (if applicable)
- Issue description and urgency
- Preferred response timeframe
- Contact person and phone/email

Write the email body only. Do NOT include subject line or greeting.""",

    "owner_briefing": """You are PropOps Draft AI, writing concise operational briefings for property owners on incidents.

TONE GUIDELINES:
- Professional and matter-of-fact
- Lead with the incident title and status
- Provide facts only, no speculation
- Include any financial impact if known
- Suggest next steps or owner action required
- Be concise (under 200 words)

STRUCTURE:
1. Incident title and current status
2. Affected property/unit and tenant (if applicable)
3. Issue summary and current status
4. Owner action required (if any)
5. Timeline for resolution

Write the briefing body only.""",
}


class DraftResult(BaseModel):
    """Result of draft generation with safety validation."""
    model_config = ConfigDict(from_attributes=True)
    
    success: bool
    subject: Optional[str] = None
    body: Optional[str] = None
    error: Optional[str] = None
    safety_issues: list[str] = []


def scan_for_safety_violations(text: str) -> list[str]:
    """
    Scan generated text for safety pattern violations.
    
    Args:
        text: The generated draft text to validate
        
    Returns:
        List of safety issues found (empty if safe)
    """
    violations = []
    text_lower = text.lower()
    
    # Check liability patterns
    for pattern in LIABILITY_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            violations.append(f"Liability admission detected: {pattern}")
    
    # Check financial confirmation patterns
    for pattern in FINANCIAL_CONFIRMATION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            violations.append(f"Financial confirmation detected: {pattern}")
    
    # Check time confirmation patterns
    for pattern in TIME_CONFIRMATION_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            violations.append(f"Specific time confirmation detected: {pattern}")
    
    return violations


async def generate_draft(
    incident_title: str,
    incident_context: str,
    draft_type: str = "tenant_reply",
    recipient_email: Optional[str] = None,
) -> DraftResult:
    """
    Generate an AI draft response using Claude.
    
    SECURITY-REVIEW: Output is always validated against safety patterns before returning.
    
    Args:
        incident_title: Brief title of the incident
        incident_context: Full context of the incident/email thread
        draft_type: Type of draft (tenant_reply, vendor_outreach, owner_briefing)
        recipient_email: Email of the intended recipient (logged for audit)
        
    Returns:
        DraftResult with success flag, draft content, and any safety issues
    """
    if draft_type not in DRAFT_SYSTEM_PROMPTS:
        return DraftResult(
            success=False,
            error=f"Unknown draft_type: {draft_type}. Must be one of {list(DRAFT_SYSTEM_PROMPTS.keys())}"
        )
    
    if not settings.anthropic_api_key:
        logger.error("Anthropic API key not configured")
        return DraftResult(
            success=False,
            error="AI service not configured (ANTHROPIC_API_KEY missing)"
        )
    
    system_prompt = DRAFT_SYSTEM_PROMPTS[draft_type]
    user_prompt = f"""Incident: {incident_title}

Context:
{incident_context}

Generate a professional draft response following the safety rules above. Output ONLY the draft body text. No preamble, no closing, no explanations."""
    
    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        
        draft_body = message.content[0].text.strip()
        
        # SECURITY-REVIEW: Validate generated content against safety patterns
        safety_issues = scan_for_safety_violations(draft_body)
        
        if safety_issues:
            logger.warning(
                f"Draft rejected due to safety violations for incident '{incident_title}' "
                f"(recipient: {recipient_email}): {safety_issues}"
            )
            return DraftResult(
                success=False,
                error="Draft rejected: contains unsafe content. Human review required.",
                safety_issues=safety_issues
            )
        
        logger.info(
            f"Draft generated successfully for incident '{incident_title}' "
            f"(type: {draft_type}, recipient: {recipient_email})"
        )
        
        return DraftResult(
            success=True,
            body=draft_body,
            safety_issues=[]
        )
    
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}", exc_info=True)
        return DraftResult(
            success=False,
            error=f"AI service error: {str(e)[:100]}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in generate_draft: {e}", exc_info=True)
        return DraftResult(
            success=False,
            error="Internal error generating draft — see logs"
        )
---