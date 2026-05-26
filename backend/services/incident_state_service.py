"""Incident state management service.

Handles state transitions, validation, audit logging, and notifications.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.core.state_machine import (
    validate_transition,
    get_valid_transitions,
    IncidentStatus,
)
from backend.models.incident import Incident
from backend.models.audit_log import log_incident_action
from backend.services.notification import notify_emergency_incident

logger = logging.getLogger(__name__)


class StateTransitionError(Exception):
    """Raised when state transition validation fails."""
    pass


async def transition_incident_status(
    db: AsyncSession,
    incident_id: str,
    new_status: str,
    actor: str,
    reason: Optional[str] = None,
    allow_override: bool = False,
) -> dict:
    """
    Transition an incident to a new status with full validation and logging.

    Args:
        db: AsyncSession
        incident_id: Incident UUID as string
        new_status: Target status
        actor: Who is making the transition (e.g., "human:user@email.com")
        reason: Optional reason for transition
        allow_override: If True, allow re-opening from RESOLVED

    Returns:
        Dict with incident_id, from_status, to_status, timestamp

    Raises:
        StateTransitionError: If transition is invalid
    """
    # Fetch incident
    incident_uuid = UUID(incident_id)
    result = await db.execute(
        select(Incident).where(Incident.id == incident_uuid)
    )
    incident = result.scalar_one_or_none()
    if not incident:
        raise StateTransitionError(f"Incident {incident_id} not found")

    current_status = incident.status
    new_status_upper = new_status.upper()

    # Validate transition
    is_valid, error_msg = validate_transition(
        current_status,
        new_status_upper,
        allow_override=allow_override,
    )
    if not is_valid:
        logger.warning(f"Invalid transition attempt: {current_status} → {new_status_upper}: {error_msg}")
        raise StateTransitionError(error_msg)

    # No-op if same status
    if current_status == new_status_upper:
        return {
            "incident_id": str(incident.id),
            "from_status": current_status,
            "to_status": new_status_upper,
            "changed": False,
            "timestamp": incident.updated_at.isoformat(),
        }

    # Update incident
    incident.status = new_status_upper
    incident.updated_at = datetime.now(timezone.utc)

    # Set resolved_at if moving to RESOLVED
    if new_status_upper == IncidentStatus.RESOLVED.value:
        incident.resolved_at = datetime.now(timezone.utc)

    # Audit log entry
    audit_details = {
        "from_status": current_status,
        "to_status": new_status_upper,
        "reason": reason or "",
    }
    await log_incident_action(
        db=db,
        org_id=str(incident.org_id),
        incident_id=incident_id,
        action="status_change",
        actor=actor,
        details=audit_details,
    )

    await db.commit()

    logger.info(
        f"incident_state: transitioned {incident_id} from {current_status} to {new_status_upper} by {actor}"
    )

    return {
        "incident_id": str(incident.id),
        "from_status": current_status,
        "to_status": new_status_upper,
        "changed": True,
        "timestamp": incident.updated_at.isoformat(),
    }


async def create_incident_with_state(
    db: AsyncSession,
    incident: Incident,
    actor: str = "ai:triage",
) -> str:
    """
    Create a new incident and log creation + initial state.

    Args:
        db: AsyncSession
        incident: Incident model instance
        actor: Who created it

    Returns:
        incident_id as string
    """
    db.add(incident)
    await db.flush()

    # Log creation
    await log_incident_action(
        db=db,
        org_id=str(incident.org_id),
        incident_id=str(incident.id),
        action="created",
        actor=actor,
        details={
            "title": incident.title,
            "category": incident.category,
            "urgency": incident.urgency,
            "initial_status": incident.status,
        },
    )

    # EMERGENCY incidents trigger notifications
    if incident.urgency == "EMERGENCY":
        await log_incident_action(
            db=db,
            org_id=str(incident.org_id),
            incident_id=str(incident.id),
            action="emergency_notification",
            actor="system:automation",
            details={"reason": "EMERGENCY urgency level"},
        )
        await notify_emergency_incident(
            incident_id=str(incident.id),
            title=incident.title,
            property_name=None,  # Would be populated from property_id if available
            org_email=None,  # Would come from organization settings
        )

    await db.commit()
    logger.info(f"incident_state: created incident {incident.id} with status {incident.status}")
    return str(incident.id)


async def get_incident_history(
    db: AsyncSession,
    incident_id: str,
) -> list[dict]:
    """
    Get audit trail for an incident.

    Args:
        db: AsyncSession
        incident_id: Incident UUID as string

    Returns:
        List of audit log entries in chronological order
    """
    from backend.models.audit_log import AuditLog

    incident_uuid = UUID(incident_id)
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.incident_id == incident_uuid)
        .order_by(AuditLog.created_at.asc())
    )
    logs = result.scalars().all()

    return [
        {
            "id": str(log.id),
            "action": log.action,
            "actor": log.actor,
            "details": log.details,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
