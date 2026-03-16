"""link proposal templates to call library entries

Revision ID: 20260314_0047
Revises: 20260314_0046
Create Date: 2026-03-14 11:15:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260314_0047"
down_revision = "20260314_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposal_templates", sa.Column("call_library_entry_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_proposal_templates_call_library_entry_id",
        "proposal_templates",
        "proposal_call_library_entries",
        ["call_library_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_proposal_templates_call_library_entry_id", "proposal_templates", ["call_library_entry_id"])


def downgrade() -> None:
    op.drop_index("ix_proposal_templates_call_library_entry_id", table_name="proposal_templates")
    op.drop_constraint("fk_proposal_templates_call_library_entry_id", "proposal_templates", type_="foreignkey")
    op.drop_column("proposal_templates", "call_library_entry_id")
