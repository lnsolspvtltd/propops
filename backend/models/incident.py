"""Incident and AIDraft models."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Optional
from sqlalchemy import String, Text, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.core.database import Base


class Incident(Base):
    """Core incident/thread model."""
    __tablename__ = "incidents"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    property_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("properties.id"))
    unit_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("units.id"))
    thread_id: Mapped[UUID] = mapped_column(default=uuid4, index=True)
    
    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    urgency: Mapped[str] = mapped_column(String(50), default="MEDIUM", index=True)
    status: Mapped[str] = mapped_column(String(50), default="OPEN", index=True)
    
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)
    
    source_channel: Mapped[Optional[str]] = mapped_column(String(50))
    source_address: Mapped[Optional[str]] = mapped_column(String(255))
    raw_message: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AIDraft(Base):
    """AI-generated draft response awaiting approval."""
    __tablename__ = "ai_drafts"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"), index=True)
    
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    recipient_email: Mapped[str] = mapped_column(String(255))
    
    status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    # pending | approved | rejected | sent | failed
    
    approved_by: Mapped[Optional[str]] = mapped_column(String(255))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    rejected_by: Mapped[Optional[str]] = mapped_column(String(255))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
---