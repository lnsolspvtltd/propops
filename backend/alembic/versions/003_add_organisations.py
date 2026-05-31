"""No-op: organisations table is created by 003_add_orgs (merged via 004_merge_heads)."""
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    pass  # organisations table created by 003_add_orgs; 004_merge_heads reconciles both heads


def downgrade() -> None:
    pass  # nothing to undo
