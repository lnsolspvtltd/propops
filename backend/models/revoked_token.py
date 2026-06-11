"""Revoked JWT identifiers — DB-backed blocklist shared across workers."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from backend.models.base import Base


class RevokedToken(Base):
    """JWT jti blocklist entry with optional expiry for TTL cleanup.

    Indexes are defined in Alembic migration 004 (Postgres partial index).
    """

    __tablename__ = "revoked_tokens"

    jti = Column(String(36), primary_key=True)
    revoked_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<RevokedToken jti={self.jti!r} expires_at={self.expires_at!r}>"
