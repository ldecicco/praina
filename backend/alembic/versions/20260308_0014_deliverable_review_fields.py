"""deliverable review fields

Revision ID: 20260308_0014
Revises: 20260308_0013
Create Date: 2026-03-08 18:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260308_0014"
down_revision = "20260308_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deliverables", sa.Column("review_due_month", sa.Integer(), nullable=True))
    op.add_column("deliverables", sa.Column("review_owner_member_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_deliverables_review_owner_member_id"), "deliverables", ["review_owner_member_id"], unique=False)
    op.create_foreign_key(
        "fk_deliverables_review_owner_member_id_team_members",
        "deliverables",
        "team_members",
        ["review_owner_member_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_deliverables_review_owner_member_id_team_members", "deliverables", type_="foreignkey")
    op.drop_index(op.f("ix_deliverables_review_owner_member_id"), table_name="deliverables")
    op.drop_column("deliverables", "review_owner_member_id")
    op.drop_column("deliverables", "review_due_month")
