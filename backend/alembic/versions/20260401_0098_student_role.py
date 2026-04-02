"""student role

Revision ID: 20260401_0098
Revises: 20260401_0097
Create Date: 2026-04-01 21:00:00.000000
"""

from __future__ import annotations


revision = "20260401_0098"
down_revision = "20260401_0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # platform_role is a String(32) column; no schema change needed
    # for the new "student" value.
    pass


def downgrade() -> None:
    pass
