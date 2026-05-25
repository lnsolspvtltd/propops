"""Inbox API routes — manual email submission for testing."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.database import get_db
from backend.services.inbox_poller import process_email

router = APIRouter()


class InboundEmailRequest(BaseModel):
    sender: str
    subject: str = ""
    body: str
    org_id: str = "00000000-0000-0000-0000-000000000001"


@router.post("/simulate")
async def simulate_inbound_email(req: InboundEmailRequest, db: AsyncSession = Depends(get_db)):
    """Simulate an inbound email for testing the triage pipeline."""
    incident_id = await process_email(
        db=db, org_id=req.org_id,
        sender=req.sender, subject=req.subject,
        body=req.body, message_id=f"sim-{req.sender}",
    )
    return {"incident_id": incident_id, "status": "processed"}