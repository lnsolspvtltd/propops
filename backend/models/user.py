"""SQLAlchemy model for a PropOps user (multi-tenant auth)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class User(Base):
    """Authenticated user scoped to an Organisation.

    Passwords are stored as bcrypt hashes (60 chars output; 72-char column is
    a tight upper bound matching bcrypt's own input limit — intentional).

    Indexes are defined in Alembic migration 005.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # bcrypt output is 60 chars; 72 is a tight upper bound that matches
    # bcrypt's own input limit and is intentional — not a mistake.
    hashed_password: Mapped[str] = mapped_column(String(72), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reset_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} org_id={self.org_id} role={self.role!r}>"
