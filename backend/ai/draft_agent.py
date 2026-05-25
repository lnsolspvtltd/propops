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