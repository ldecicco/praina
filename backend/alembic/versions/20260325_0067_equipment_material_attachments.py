"""equipment material attachments

Revision ID: 20260325_0067
Revises: 20260325_0066
Create Date: 2026-03-25 12:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260325_0067"
down_revision = "20260325_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("equipment_materials", sa.Column("attachment_path", sa.String(length=512), nullable=True))
    op.add_column("equipment_materials", sa.Column("attachment_filename", sa.String(length=255), nullable=True))
    op.add_column("equipment_materials", sa.Column("attachment_mime_type", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("equipment_materials", "attachment_mime_type")
    op.drop_column("equipment_materials", "attachment_filename")
    op.drop_column("equipment_materials", "attachment_path")
