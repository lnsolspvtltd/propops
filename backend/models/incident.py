"""SQLAlchemy models for PropOps.

All datetime fields use timezone-aware UTC (datetime.now(timezone.utc)).
All ID fields use UUID primary keys with gen_random_uuid() default.
Soft deletes via deleted_at column (never hard delete).
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email_domain = Column(String(255))
    plan = Column(String(50), default="beta")
    unit_count = Column(Integer, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    properties = relationship("Property", back_populates="org", cascade="all, delete")
    incidents = relationship("Incident", back_populates="org")


class Property(Base):
    __tablename__ = "properties"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    address = Column(Text)
    city = Column(String(100))
    unit_count = Column(Integer, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    org = relationship("Organization", back_populates="properties")
    units = relationship("Unit", back_populates="property_")


class Unit(Base):
    __tablename__ = "units"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(
        UUID(as_uuid=True),
        ForeignKey("properties.id"),
        nullable=False,
        index=True,
    )
    unit_number = Column(String(50), nullable=False)
    tenant_name = Column(String(255))
    tenant_email = Column(String(255), index=True)
    tenant_phone = Column(String(50))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    property_ = relationship("Property", back_populates="units")


class Incident(Base):
    __tablename__ = "incidents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"))
    unit_id = Column(UUID(as_uuid=True), ForeignKey("units.id"))
    thread_id = Column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    category = Column(String(100), index=True)
    urgency = Column(String(50), index=True)
    status = Column(String(50), default="OPEN", index=True)
    ai_summary = Column(Text)
    ai_confidence = Column(Float)
    source_channel = Column(String(50), index=True)
    source_address = Column(String(255))
    raw_message = Column(Text)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    resolved_at = Column(DateTime(timezone=True))
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    org = relationship("Organization", back_populates="incidents")
    
    __table_args__ = (
        Index("idx_incidents_org_status_created", "org_id", "status", "created_at"),
        Index("idx_incidents_thread_id", "thread_id"),
    )


class AIDraft(Base):
    __tablename__ = "ai_drafts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id"),
        nullable=False,
        index=True,
    )
    draft_text = Column(Text, nullable=False)
    status = Column(String(50), default="PENDING_REVIEW", index=True)
    approved_by = Column(String(255))
    approved_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)


class CommunicationLog(Base):
    __tablename__ = "communication_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id"),
        nullable=False,
        index=True,
    )
    message_id = Column(String(500), unique=True, nullable=True, index=True)
    direction = Column(String(50), nullable=False)  # INBOUND, OUTBOUND
    source = Column(String(50), nullable=False)  # email, sms, web, etc.
    from_addr = Column(String(255))
    to_addr = Column(String(255))
    subject = Column(String(500))
    body_preview = Column(Text)
    metadata = Column(JSONB, default={})
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    __table_args__ = (
        Index("idx_communication_logs_incident_created", "incident_id", "created_at"),
    )
---