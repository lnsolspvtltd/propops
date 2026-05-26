"""SQLAlchemy 2.0+ models for PropOps — using Mapped[] and mapped_column()."""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Float, DateTime, ForeignKey, Integer, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


class Organization(Base):
    """PM company organization."""
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email_domain: Mapped[Optional[str]] = mapped_column(String(255))
    plan: Mapped[str] = mapped_column(String(50), default="beta")
    unit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    properties: Mapped[list["Property"]] = relationship(back_populates="org", cascade="all, delete")
    incidents: Mapped[list["Incident"]] = relationship(back_populates="org")

    __table_args__ = (
        CheckConstraint("plan IN ('beta', 'starter', 'pro')"),
        Index("idx_organizations_deleted", "deleted_at"),
        Index("idx_organizations_email_domain", "email_domain"),
    )


class Property(Base):
    """Building/property managed by organization."""
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    province: Mapped[Optional[str]] = mapped_column(String(50))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    unit_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    org: Mapped["Organization"] = relationship(back_populates="properties")
    units: Mapped[list["Unit"]] = relationship(back_populates="property_")

    __table_args__ = (
        Index("idx_properties_org", "org_id"),
        Index("idx_properties_deleted", "deleted_at"),
    )


class Unit(Base):
    """Tenant-linked unit with contact info."""
    __tablename__ = "units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False
    )
    unit_number: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_name: Mapped[Optional[str]] = mapped_column(String(255))
    tenant_email: Mapped[Optional[str]] = mapped_column(String(255))
    tenant_phone: Mapped[Optional[str]] = mapped_column(String(50))
    lease_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    lease_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    property_: Mapped["Property"] = relationship(back_populates="units")

    __table_args__ = (
        Index("idx_units_property", "property_id"),
        Index("idx_units_tenant_email", "tenant_email"),
        Index("idx_units_deleted", "deleted_at"),
    )


class Incident(Base):
    """Unified Operational Thread (UOTL) — core incident tracking."""
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    property_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"))
    unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("units.id"))
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    urgency: Mapped[str] = mapped_column(String(50), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(50), default="OPEN")
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)
    source_channel: Mapped[Optional[str]] = mapped_column(String(50))
    source_address: Mapped[Optional[str]] = mapped_column(String(255))
    raw_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    org: Mapped["Organization"] = relationship(back_populates="incidents")
    drafts: Mapped[list["AIDraft"]] = relationship(back_populates="incident", cascade="all, delete")
    comm_logs: Mapped[list["CommunicationLog"]] = relationship(back_populates="incident", cascade="all, delete")

    __table_args__ = (
        CheckConstraint("category IS NULL OR category IN ('maintenance', 'billing', 'noise', 'lease', 'move_in', 'move_out', 'general')"),
        CheckConstraint("urgency IN ('EMERGENCY', 'HIGH', 'MEDIUM', 'LOW')"),
        CheckConstraint("status IN ('OPEN', 'PENDING_APPROVAL', 'DISPATCH_READY', 'DISPATCHED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')"),
        CheckConstraint("source_channel IS NULL OR source_channel IN ('email', 'sms', 'portal', 'manual')"),
        CheckConstraint("ai_confidence IS NULL OR (ai_confidence >= 0 AND ai_confidence <= 1)"),
        Index("idx_incidents_org_status", "org_id", "status"),
        Index("idx_incidents_thread", "thread_id"),
        Index("idx_incidents_urgency_status", "urgency", "status"),
        Index("idx_incidents_property", "property_id"),
        Index("idx_incidents_deleted", "deleted_at"),
    )


class AIDraft(Base):
    """AI-generated draft awaiting human approval."""
    __tablename__ = "ai_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    draft_type: Mapped[Optional[str]] = mapped_column(String(50))
    recipient_email: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    ai_model: Mapped[Optional[str]] = mapped_column(String(100))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    incident: Mapped["Incident"] = relationship(back_populates="drafts")

    __table_args__ = (
        CheckConstraint("draft_type IS NULL OR draft_type IN ('tenant_reply', 'vendor_outreach', 'escalation')"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'sent')"),
        CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)"),
        Index("idx_drafts_incident", "incident_id"),
        Index("idx_drafts_status", "status"),
        Index("idx_drafts_created", "created_at"),
    )


class CommunicationLog(Base):
    """All inbound/outbound messages linked to incident."""
    __tablename__ = "communication_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    thread_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    sender: Mapped[Optional[str]] = mapped_column(String(255))
    recipient: Mapped[Optional[str]] = mapped_column(String(255))
    subject: Mapped[Optional[str]] = mapped_column(String(500))
    body: Mapped[Optional[str]] = mapped_column(Text)
    raw_headers: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    incident: Mapped["Incident"] = relationship(back_populates="comm_logs")

    __table_args__ = (
        CheckConstraint("direction IN ('inbound', 'outbound')"),
        CheckConstraint("channel IN ('email', 'sms', 'portal')"),
        Index("idx_comm_logs_incident", "incident_id"),
        Index("idx_comm_logs_thread", "thread_id"),
        Index("idx_comm_logs_created", "created_at"),
    )


class AuditLog(Base):
    """Every action with actor (ai or human) — immutable audit trail."""
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"))
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[Optional[str]] = mapped_column(String(255))  # e.g., "ai:triage" or "human:user@example.com"
    details: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_logs_org", "org_id"),
        Index("idx_audit_logs_incident", "incident_id"),
        Index("idx_audit_logs_created", "created_at"),
    )
```

---