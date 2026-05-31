"""SQLAlchemy model for a PropOps user (multi-tenant auth)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class User(Base):
    """Authenticated user scoped to an Organisation.

    Passwords are stored as bcrypt hashes (60 chars output); String(255)
    supports bcrypt and future algorithm migration (Argon2id = 95+ chars).

    Indexes are defined in Alembic migration 005.
    """

    __tablename__ = "users"

    # Composite unique constraint: per-org email uniqueness while allowing the
    # same email across different organisations (multi-tenant isolation).
    __table_args__ = (
        UniqueConstraint("email", "org_id", name="uq_user_email_org"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # String(255) supports bcrypt (60 chars) and future algorithm migration
    # (Argon2id = 95+ chars).
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="member", server_default="member"
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    last_verification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reset_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} org_id={self.org_id} role={self.role!r}>"
