"""Add revoked_tokens table for JWT jti blocklist.

Revision ID: 004
Revises: 003

Note: partial index below is PostgreSQL-specific (PropOps production DB).
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(36), primary_key=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_revoked_tokens_expires_notnull "
        "ON revoked_tokens (expires_at) WHERE expires_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("idx_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
