"""Add invites table for org member invitation flow.

Revision ID: 007
Revises: 006

Creates the invites table which tracks pending email invitations to join an
organisation.  Each invite is identified by a UUID jti (JWT identifier) so
that accept-links can be validated and revoked without a separate blocklist.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        # jti uniqueness enforced at DB level — one active link per jti,
        # preventing replay attacks on accept URLs.
        sa.Column("jti", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # SECURITY-NOTE: Index on org_id allows efficient listing of all pending
    # invites for a given organisation — required for admin dashboards and
    # duplicate-invite checks without full-table scans.
    op.create_index("idx_invites_org_id", "invites", ["org_id"])

    # SECURITY-NOTE: Index on jti supports O(1) lookup when a recipient clicks
    # an invite link.  The jti is the primary verification token in the accept
    # URL; fast lookup is essential to avoid timing attacks and keep latency low.
    op.create_index("idx_invites_jti", "invites", ["jti"])


def downgrade() -> None:
    op.drop_index("idx_invites_jti", table_name="invites")
    op.drop_index("idx_invites_org_id", table_name="invites")
    op.drop_table("invites")
