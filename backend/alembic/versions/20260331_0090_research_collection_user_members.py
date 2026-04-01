"""Allow research collections to store direct user members.

Revision ID: 20260331_0090
Revises: 20260331_0089
Create Date: 2026-03-31 19:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0090"
down_revision = "20260331_0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("research_collection_members", "member_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("research_collection_members", sa.Column("user_account_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_research_collection_members_user_account_id"),
        "research_collection_members",
        ["user_account_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_research_collection_members_user_account_id_user_accounts",
        "research_collection_members",
        "user_accounts",
        ["user_account_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_research_collection_members_user_account_id_user_accounts",
        "research_collection_members",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_research_collection_members_user_account_id"), table_name="research_collection_members")
    op.drop_column("research_collection_members", "user_account_id")
    op.alter_column("research_collection_members", "member_id", existing_type=sa.UUID(), nullable=False)
