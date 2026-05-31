"""Demo-only routes for seeding data and simulating email ingestion.

SECURITY: Only available when ENVIRONMENT=development.
Never ship these in production.
"""
import logging
import uuid
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.auth import get_current_user
from backend.core.database import get_db
from backend.models.incident import Incident, AIDraft

logger = logging.getLogger(__name__)

DEFAULT_DEMO_ORG = uuid.UUID(settings.demo_org_id)


def _check_dev_only():
    if settings.environment != "development":
        raise HTTPException(status_code=403, detail={"error": "Demo endpoints are development-only"})


async def _require_development() -> None:
    """Router-level guard: demo routes never register in production."""
    _check_dev_only()


router = APIRouter(
    prefix="/api/v1/demo",
    tags=["demo"],
    dependencies=[Depends(_require_development)],
)

DEMO_SCENARIOS = {
    "emergency_leak": {
        "title": "Water leak flooding kitchen — Apt 4B",
        "category": "maintenance", "urgency": "EMERGENCY",
        "source": "john.smith@tenant.example.com",
        "raw_message": "Hi,\n\nMy kitchen ceiling has been dripping water since last night and it's getting MUCH worse. There is now a puddle on the floor. I have a towel down but it's soaked through.\n\nThis needs urgent attention ASAP. I have young children at home.\n\nJohn Smith\nApt 4B",
        "draft_subject": "Re: Water Leak — Apt 4B [URGENT]",
        "draft_body": "Dear John,\n\nThank you for alerting us to this immediately. We understand this is extremely stressful, especially with young children at home.\n\nWe have escalated this to emergency maintenance priority. A licensed plumber will be on-site within 2 hours to assess and stop the leak.\n\nIn the meantime:\n• Do not use the affected area\n• Keep the towel down and place a bucket if available\n• If the ceiling shows signs of structural damage, please move to another room\n\nWe will keep you updated as this progresses. You can reach us directly at the number below.\n\nPropOps Maintenance Team",
    },
    "lock_broken": {
        "title": "Front door lock broken — cannot secure apartment",
        "category": "maintenance", "urgency": "HIGH",
        "source": "sarah.k@tenant.example.com",
        "raw_message": "The lock on my front door stopped working this morning. I literally cannot lock my door before leaving for work. This is a serious security issue.\n\nPlease fix this today.\n\nSarah K\nUnit 7",
        "draft_subject": "Re: Front Door Lock — Unit 7",
        "draft_body": "Dear Sarah,\n\nWe take security issues very seriously. We have scheduled a locksmith to attend Unit 7 today between 2pm and 4pm.\n\nIn the meantime, if you need to leave your apartment unsecured, please let us know and we can arrange temporary storage for any valuables.\n\nThe locksmith will either repair or replace the lock. There is no cost to you for this repair.\n\nKind regards,\nPropOps Maintenance",
    },
    "noise_complaint": {
        "title": "Persistent noise from upstairs neighbour — 3 nights",
        "category": "noise", "urgency": "MEDIUM",
        "source": "emily.r@tenant.example.com",
        "raw_message": "Hi,\n\nI'm writing to complain about the noise from the apartment above mine (Unit 12). For the past 3 nights, there has been loud stomping and music after midnight. I have work early in the morning and this is affecting my sleep.\n\nCan you please do something about this?\n\nEmily R\nUnit 11",
        "draft_subject": "Re: Noise Concern — Unit 11",
        "draft_body": "Dear Emily,\n\nThank you for bringing this to our attention. We completely understand how disruptive this must be, especially on work nights.\n\nWe will contact the tenant in Unit 12 directly today to discuss quiet hours (11pm–8am) in line with the tenancy agreement. We take noise complaints seriously and will ensure this is addressed.\n\nIf the issue continues after today, please do not hesitate to contact us again. We can arrange mediation if needed.\n\nWe appreciate your patience and apologise for the disruption.\n\nKind regards,\nPropOps Team",
    },
    "lease_question": {
        "title": "Lease renewal query — when does my tenancy end?",
        "category": "lease", "urgency": "LOW",
        "source": "david.m@tenant.example.com",
        "raw_message": "Hi,\n\nCould you let me know when my current lease expires? I'd like to know my options for renewal and whether the rent will change.\n\nThanks,\nDavid M\nUnit 3",
        "draft_subject": "Re: Lease Renewal — Unit 3",
        "draft_body": "Dear David,\n\nThank you for your enquiry. Your current tenancy agreement is due for review in the coming weeks. Our lettings team will be in touch with the renewal terms and any updates to the rental amount.\n\nIn the meantime, please feel free to reach out if you have any questions. We value you as a tenant and look forward to continuing our tenancy arrangement.\n\nKind regards,\nPropOps Lettings Team",
    },
}

SEED_INCIDENTS = [
    {**DEMO_SCENARIOS["emergency_leak"], "status": "OPEN"},
    {**DEMO_SCENARIOS["lock_broken"], "status": "OPEN"},
    {**DEMO_SCENARIOS["noise_complaint"], "status": "OPEN"},
    {**DEMO_SCENARIOS["lease_question"], "status": "OPEN"},
    {
        "title": "No hot water — 3 days without heating", "category": "maintenance", "urgency": "HIGH",
        "source": "familia.g@tenant.example.com", "status": "OPEN",
        "raw_message": "This is the third day without hot water. I have two young children and this is unacceptable. Please fix this immediately.\n\nFamilia G, Apt 6",
        "draft_subject": "Re: Hot Water — Apt 6 [Urgent]",
        "draft_body": "Dear Familia,\n\nWe sincerely apologise for this situation. We understand how essential hot water is, particularly with young children.\n\nOur plumber has been booked for this afternoon between 3pm and 5pm to inspect the boiler. If parts are needed, we will expedite the order.\n\nWe will call ahead 30 minutes before arrival. Please accept our apologies for the inconvenience.\n\nPropOps Maintenance",
    },
    {
        "title": "Dishwasher standing water — not draining", "category": "maintenance", "urgency": "MEDIUM",
        "source": "mark.p@tenant.example.com", "status": "OPEN",
        "raw_message": "My dishwasher has standing water after every cycle for the past week. I've checked the filter and it looks clear. Can you send someone to look at it?\n\nMark P, Unit 9",
        "draft_subject": "Re: Dishwasher — Unit 9",
        "draft_body": "Dear Mark,\n\nThank you for reporting this. A blocked or faulty drain pump is the most common cause of this issue and can be repaired quickly.\n\nWe have booked an appliance engineer for next Tuesday between 9am and 12pm. Please ensure someone is available to provide access.\n\nKind regards,\nPropOps Maintenance",
    },
    {
        "title": "Guest parking enquiry", "category": "general", "urgency": "LOW",
        "source": "nina.w@tenant.example.com", "status": "OPEN",
        "raw_message": "Hi, my family is visiting this weekend. Can they park in the car park? And if so, is there a visitor permit needed?\n\nNina W, Unit 15",
        "draft_subject": "Re: Guest Parking — Unit 15",
        "draft_body": "Dear Nina,\n\nGreat news — visitor parking is available on-site. Guests can park in the bays marked 'Visitor' near the main entrance.\n\nVisitor permits are required between 8am and 8pm on weekdays. You can collect a permit from the management office or we can email you one.\n\nEnjoy your family visit!\n\nKind regards,\nPropOps Team",
    },
    {
        "title": "Heating fixed — thank you for the quick response!",
        "category": "maintenance", "urgency": "LOW",
        "source": "chen.l@tenant.example.com", "status": "CLOSED",
        "raw_message": "Hi, just wanted to say thank you for sending the engineer so quickly yesterday. The heating is working perfectly now. Great service!\n\nChen L, Unit 2",
        "draft_subject": "Re: Thank You — Unit 2",
        "draft_body": "Dear Chen,\n\nThank so much for taking the time to share this feedback — it really means a lot to our team.\n\nWe're delighted the heating is back to working order and that the response time met your expectations. We'll pass your kind words on to the engineer.\n\nDo not hesitate to get in touch if there is anything else we can help with.\n\nWarm regards,\nPropOps Team",
    },
]


class SeedResponse(BaseModel):
    incidents_created: int
    drafts_created: int
    message: str


class SimulateRequest(BaseModel):
    scenario: str = "emergency_leak"


class SimulateResponse(BaseModel):
    incident_id: str
    draft_id: str
    urgency: str
    processing_time_ms: int


@router.post("/seed", response_model=SeedResponse)
async def seed_demo_data(
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> SeedResponse:
    """Inject realistic demo incidents with pending AI drafts. Idempotent."""
    _check_dev_only()

    # Check if already seeded
    existing = (await db.execute(
        select(Incident).where(Incident.source_address.like("%@tenant.example.com")).limit(1)
    )).scalar_one_or_none()
    if existing:
        return SeedResponse(incidents_created=0, drafts_created=0, message="Demo data already seeded")

    incidents_created = 0
    drafts_created = 0
    now = datetime.now(timezone.utc)

    for i, scenario in enumerate(SEED_INCIDENTS):
        inc = Incident(
            id=uuid.uuid4(),
            org_id=DEFAULT_DEMO_ORG,
            title=scenario["title"],
            category=scenario["category"],
            urgency=scenario["urgency"],
            status=scenario.get("status", "OPEN"),
            source_address=scenario["source"],
            raw_message=scenario["raw_message"],
            ai_summary=scenario["draft_body"][:200] + "...",
            ai_confidence=0.92,
            source_channel="email",
            created_at=datetime.fromtimestamp(now.timestamp() - (i * 1800), tz=timezone.utc),
        )
        db.add(inc)
        await db.flush()
        incidents_created += 1

        if scenario.get("status", "OPEN") != "CLOSED":
            draft = AIDraft(
                id=uuid.uuid4(),
                incident_id=inc.id,
                draft_type="reply",
                recipient_email=scenario["source"],
                subject=scenario["draft_subject"],
                body=scenario["draft_body"],
                ai_model="claude-sonnet-4-5",
                confidence=0.91,
                status="pending",
                created_at=datetime.fromtimestamp(now.timestamp() - (i * 1800) + 15, tz=timezone.utc),
            )
            db.add(draft)
            drafts_created += 1
        elif scenario.get("status") == "CLOSED":
            draft = AIDraft(
                id=uuid.uuid4(), incident_id=inc.id, draft_type="reply",
                recipient_email=scenario["source"],
                subject=scenario["draft_subject"], body=scenario["draft_body"],
                ai_model="claude-sonnet-4-5", confidence=0.91,
                status="approved", approved_by="founder",
                approved_at=datetime.fromtimestamp(now.timestamp() - 3600, tz=timezone.utc),
                sent_at=datetime.fromtimestamp(now.timestamp() - 3500, tz=timezone.utc),
            )
            db.add(draft)

    await db.flush()
    return SeedResponse(
        incidents_created=incidents_created,
        drafts_created=drafts_created,
        message=f"Seeded {incidents_created} incidents and {drafts_created} pending drafts",
    )


@router.post("/simulate-email", response_model=SimulateResponse)
async def simulate_email(
    req: SimulateRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> SimulateResponse:
    """Run a realistic scenario through the FULL AI pipeline (triage -> draft).

    For live investor demos. Synchronous so the response contains the result.
    Expected time: 2-4s (Claude API calls).
    """
    _check_dev_only()

    scenario = DEMO_SCENARIOS.get(req.scenario, DEMO_SCENARIOS["emergency_leak"])
    start = time.time()

    try:
        from backend.ai.triage_agent import triage_message
        triage = await triage_message(scenario["raw_message"], scenario["source"])
    except Exception as e:
        logger.warning("Triage failed, using scenario defaults: %s", e)
        triage = None

    inc = Incident(
        id=uuid.uuid4(),
        org_id=DEFAULT_DEMO_ORG,
        title=triage.title if triage else scenario["title"],
        category=triage.category if triage else scenario["category"],
        urgency=triage.urgency if triage else scenario["urgency"],
        status="OPEN",
        source_address=f"live-demo-{int(time.time())}@tenant.example.com",
        raw_message=scenario["raw_message"],
        ai_summary=triage.summary if triage else "",
        ai_confidence=triage.confidence if triage else 0.9,
        source_channel="email",
    )
    db.add(inc)
    await db.flush()

    try:
        from backend.ai.draft_agent import generate_draft
        draft_text = await generate_draft(scenario["raw_message"], triage, scenario.get("source", ""))
        draft_body = draft_text if draft_text else scenario["draft_body"]
        draft_subject = scenario["draft_subject"]
    except Exception as e:
        logger.warning("Draft generation failed, using template: %s", e)
        draft_body = scenario["draft_body"]
        draft_subject = scenario["draft_subject"]

    draft = AIDraft(
        id=uuid.uuid4(), incident_id=inc.id, draft_type="reply",
        recipient_email=scenario["source"],
        subject=draft_subject, body=draft_body,
        ai_model="claude-sonnet-4-5", confidence=0.91, status="pending",
    )
    db.add(draft)
    await db.flush()

    ms = int((time.time() - start) * 1000)
    return SimulateResponse(
        incident_id=str(inc.id), draft_id=str(draft.id),
        urgency=inc.urgency, processing_time_ms=ms,
    )