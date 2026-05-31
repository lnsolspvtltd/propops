"""Add organisations table.

Revision ID: 003
Revises: 002
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organisations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("imap_host", sa.String(255)),
        sa.Column("imap_port", sa.Integer, default=993),
        sa.Column("imap_username", sa.String(255)),
        sa.Column("imap_password_enc", sa.String(512)),
        sa.Column("imap_folder", sa.String(100), default="INBOX"),
        sa.Column("smtp_host", sa.String(255)),
        sa.Column("smtp_port", sa.Integer, default=587),
        sa.Column("smtp_username", sa.String(255)),
        sa.Column("smtp_password_enc", sa.String(512)),
        sa.Column("polling_active", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("organisations")
