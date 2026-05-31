"""Add users table for multi-tenant authentication.

Revision ID: 005
Revises: 004

Adds the users table with per-org email uniqueness, role-based access,
email verification tracking, and password reset rate-limiting columns.
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        # bcrypt output is 60 chars; 72 is a tight upper bound that matches
        # bcrypt's own input limit and is intentional — not a mistake.
        sa.Column("hashed_password", sa.String(72), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("last_verification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reset_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # SECURITY-NOTE: Unique constraint on (email, org_id) enforces per-org email
    # uniqueness while allowing the same email across different organisations —
    # required for multi-tenant isolation without global email locking.
    op.create_unique_constraint("uq_user_email_org", "users", ["email", "org_id"])

    # SECURITY-NOTE: Index on org_id accelerates all tenant-scoped user lookups
    # (e.g. list members, invite checks) and prevents full-table scans when
    # filtering by organisation — critical for row-level security enforcement.
    op.create_index("idx_users_org_id", "users", ["org_id"])

    # SECURITY-NOTE: Index on email supports fast login lookups and duplicate
    # detection during registration. Without it, every login attempt would
    # require a sequential scan of all users, leaking timing information and
    # degrading performance under load.
    op.create_index("idx_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("idx_users_org_id", table_name="users")
    op.drop_constraint("uq_user_email_org", "users", type_="unique")
    op.drop_table("users")
