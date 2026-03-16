"""partner expertise field

Revision ID: 20260310_0031
Revises: 20260310_0030
Create Date: 2026-03-10 16:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0031"
down_revision = "20260310_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("partner_organizations", sa.Column("expertise", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("partner_organizations", "expertise")
