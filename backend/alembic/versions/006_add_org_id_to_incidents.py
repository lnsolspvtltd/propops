"""No-op migration: org_id already present on incidents table.

Revision ID: 006
Revises: 005

The incidents table received an org_id column (NOT NULL, FK -> organisations.id)
in migration 001_initial_phase1_schema.  There is nothing to add here.

This placeholder migration exists to keep the revision chain contiguous so that
future migrations can chain from "006" without skipping a number.
"""
from alembic import op  # noqa: F401  (imported for Alembic to parse this file)

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # org_id was already added to incidents in migration 001_initial_phase1_schema.
    # No schema change required.
    pass


def downgrade() -> None:
    # Nothing was added in upgrade(), so nothing to remove here.
    pass
