"""SQLAlchemy models for PropOps."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey, Integer
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    properties = relationship("Property", back_populates="org", cascade="all, delete")
    incidents = relationship("Incident", back_populates="org")


class Property(Base):
    __tablename__ = "properties"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(Text)
    city = Column(String(100))
    unit_count = Column(Integer, default=0)
    org = relationship("Organization", back_populates="properties")
    units = relationship("Unit", back_populates="property_")


class Unit(Base):
    __tablename__ = "units"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)
    unit_number = Column(String(50), nullable=False)
    tenant_name = Column(String(255))
    tenant_email = Column(String(255))
    tenant_phone = Column(String(50))
    property_ = relationship("Property", back_populates="units")


class Incident(Base):
    """Core incident/thread model."""
    __tablename__ = "incidents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    property_id = Column(UUID(as_uuid=True), ForeignKey("properties.id"))
    unit_id = Column(UUID(as_uuid=True), ForeignKey("units.id"))
    thread_id = Column(UUID(as_uuid=True), default=uuid.uuid4, nullable=False)
    title = Column(String(500), nullable=False)
    category = Column(String(100))
    urgency = Column(String(50))
    status = Column(String(50), default="OPEN")
    ai_summary = Column(Text)
    ai_confidence = Column(Float)
    source_channel = Column(String(50))
    source_address = Column(String(255))
    raw_message = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime(timezone=True))
    org = relationship("Organization", back_populates="incidents")
    drafts = relationship("AIDraft", back_populates="incident", cascade="all, delete")
    comm_logs = relationship("CommunicationLog", back_populates="incident", cascade="all, delete")


class AIDraft(Base):
    """AI-generated draft response awaiting approval."""
    __tablename__ = "ai_drafts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    draft_type = Column(String(50))
    recipient_email = Column(String(255))
    subject = Column(String(500))
    body = Column(Text, nullable=False)
    ai_model = Column(String(100))
    confidence = Column(Float)
    status = Column(String(50), default="pending")
    approved_by = Column(String(255))
    approved_at = Column(DateTime(timezone=True))
    rejected_by = Column(String(255))
    rejection_reason = Column(Text)
    rejected_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    incident = relationship("Incident", back_populates="drafts")


class CommunicationLog(Base):
    __tablename__ = "communication_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    thread_id = Column(UUID(as_uuid=True), nullable=False)
    direction = Column(String(10), nullable=False)
    channel = Column(String(50), nullable=False)
    sender = Column(String(255))
    recipient = Column(String(255))
    subject = Column(String(500))
    body = Column(Text)
    raw_headers = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    incident = relationship("Incident", back_populates="comm_logs")
