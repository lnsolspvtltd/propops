"""Add users table for multi-tenant authentication.

Revision ID: 005
Revises: 004

Adds the users table with per-org email uniqueness, role-based access,
email verification tracking, and password reset rate-limiting columns.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgcrypto is available for gen_random_uuid() used as server_default
    # on id columns.  pgcrypto is pre-installed on Supabase; on AWS RDS request
    # the extension via the RDS console before running this migration.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        # server_default ensures gen_random_uuid() fires even for raw SQL
        # inserts (fixtures, scripts) — not just ORM-level inserts.
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        # String(255) supports bcrypt (60 chars) and future algorithm migration
        # (Argon2id = 95+ chars).
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("last_verification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reset_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
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

    # NOTE: A bare idx_users_email index was intentionally omitted here.
    # The uq_user_email_org unique constraint already creates an implicit index
    # on (email, org_id) which covers per-org email lookups (the common case).
    # A bare email index would add write overhead and risk cross-org email
    # enumeration; it is removed to avoid write overhead and cross-org scan risk.


def downgrade() -> None:
    op.drop_index("idx_users_org_id", table_name="users")
    op.drop_constraint("uq_user_email_org", "users", type_="unique")
    op.drop_table("users")
