"""Audit log model and utilities."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.core.database import Base

logger = logging.getLogger(__name__)


class AuditLog(Base):
    """Record of all incident actions for compliance and debugging."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=True, index=True)
    action = Column(String(100), nullable=False)  # e.g., "status_change", "created", "notified"
    actor = Column(String(255), nullable=False)  # 'ai:triage', 'human:user@email.com', 'system:automation'
    details = Column(JSONB, default={})  # Structured data: {from_status, to_status, reason, ...}
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("idx_audit_logs_incident", "incident_id"),
        Index("idx_audit_logs_org", "org_id"),
        Index("idx_audit_logs_created", "created_at"),
    )


async def log_incident_action(
    db,
    org_id: str,
    incident_id: str,
    action: str,
    actor: str,
    details: Optional[dict] = None,
) -> None:
    """
    Log an incident action to audit trail.

    Args:
        db: AsyncSession
        org_id: Organization UUID
        incident_id: Incident UUID
        action: Action type (e.g., 'status_change')
        actor: Who performed the action
        details: Additional structured data
    """
    import uuid as uuid_mod

    log = AuditLog(
        org_id=uuid_mod.UUID(org_id) if isinstance(org_id, str) else org_id,
        incident_id=uuid_mod.UUID(incident_id) if isinstance(incident_id, str) else incident_id,
        action=action,
        actor=actor,
        details=details or {},
    )
    db.add(log)
    logger.info(
        f"audit_log: {action} | incident={incident_id} | actor={actor} | details={details}"
    )