"""add category and status to proposal call documents

Revision ID: 20260314_0050
Revises: 20260314_0049
Create Date: 2026-03-14 20:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260314_0050"
down_revision = "20260314_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposal_call_library_documents", sa.Column("category", sa.String(length=64), nullable=False, server_default="other"))
    op.add_column("proposal_call_library_documents", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
    op.create_index("ix_proposal_call_library_documents_category", "proposal_call_library_documents", ["category"])
    op.create_index("ix_proposal_call_library_documents_status", "proposal_call_library_documents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_proposal_call_library_documents_status", table_name="proposal_call_library_documents")
    op.drop_index("ix_proposal_call_library_documents_category", table_name="proposal_call_library_documents")
    op.drop_column("proposal_call_library_documents", "status")
    op.drop_column("proposal_call_library_documents", "category")
