"""Merge migration: reconcile dual 003 heads (003 and 003_add_orgs).

Revision ID: 004
Revises: 003, 003_add_orgs (tuple = merge)

Migration 003_add_organisations.py and 003_add_orgs.py were both authored as
independent 003-series migrations branching from 002.  This merge migration
folds them into a single linear head so that all subsequent migrations
(005+) can chain from "004" without ambiguity.

Merge migrations are structural no-ops: upgrade() and downgrade() are both
empty because the actual schema changes already live in the 003 files.
"""
from alembic import op  # noqa: F401  (imported for Alembic to parse this file)

revision = "004"
down_revision = ("003", "003_add_orgs")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge migrations are no-ops: schema changes are in the 003 files.
    pass


def downgrade() -> None:
    # Merge migrations are no-ops: nothing to undo here.
    pass
