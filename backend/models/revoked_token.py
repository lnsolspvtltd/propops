"""Revoked JWT identifiers — DB-backed blocklist shared across workers."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Index

from backend.models.base import Base


class RevokedToken(Base):
    """JWT jti blocklist entry with optional expiry for TTL cleanup."""

    __tablename__ = "revoked_tokens"

    jti = Column(String(36), primary_key=True)
    revoked_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("idx_revoked_tokens_expires_at", "expires_at"),)

    def __repr__(self) -> str:
        return f"<RevokedToken jti={self.jti!r} expires_at={self.expires_at!r}>"
