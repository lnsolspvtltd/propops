"""SQLAlchemy model for a PropOps organisation invite."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Invite(Base):
    """Pending invitation for a user to join an Organisation.

    Each invite carries a JWT jti (UUID string) that is embedded in the
    accept-link.  The jti uniqueness constraint at the DB level prevents
    replay attacks.

    Indexes are defined in Alembic migration 007.
    """

    __tablename__ = "invites"

    # Named unique constraint on jti — prevents replay attacks on accept URLs.
    # CheckConstraint ensures expires_at is always after created_at so logically
    # invalid invites can never reach the database.
    __table_args__ = (
        UniqueConstraint("jti", name="uq_invites_jti"),
        CheckConstraint("expires_at > created_at", name="ck_invites_expires_after_created"),
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
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    # jti uniqueness enforced via named constraint in __table_args__ — one
    # active link per jti, preventing replay attacks on accept URLs.
    jti: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Invite id={self.id} email={self.email!r} org_id={self.org_id}"
            f" expires_at={self.expires_at!r}>"
        )
