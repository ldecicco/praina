"""add research spaces

Revision ID: 20260331_0088
Revises: 20260329_0087
Create Date: 2026-03-31 11:40:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260331_0088"
down_revision = "20260329_0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_spaces",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.Column("linked_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["linked_project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_research_spaces_linked_project_id"), "research_spaces", ["linked_project_id"], unique=False)
    op.create_index(op.f("ix_research_spaces_owner_user_id"), "research_spaces", ["owner_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_research_spaces_owner_user_id"), table_name="research_spaces")
    op.drop_index(op.f("ix_research_spaces_linked_project_id"), table_name="research_spaces")
    op.drop_table("research_spaces")
