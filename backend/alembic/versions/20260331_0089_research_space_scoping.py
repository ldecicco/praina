"""Scope research data to research spaces.

Revision ID: 20260331_0089
Revises: 20260331_0088
Create Date: 2026-03-31 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260331_0089"
down_revision = "20260331_0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("research_collections", sa.Column("research_space_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_research_collections_research_space_id"), "research_collections", ["research_space_id"], unique=False)
    op.create_foreign_key(
        "fk_research_collections_research_space_id_research_spaces",
        "research_collections",
        "research_spaces",
        ["research_space_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("research_collections", "project_id", existing_type=sa.UUID(), nullable=True)

    op.add_column("research_references", sa.Column("research_space_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_research_references_research_space_id"), "research_references", ["research_space_id"], unique=False)
    op.create_foreign_key(
        "fk_research_references_research_space_id_research_spaces",
        "research_references",
        "research_spaces",
        ["research_space_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("research_references", "project_id", existing_type=sa.UUID(), nullable=True)

    op.add_column("research_notes", sa.Column("research_space_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_research_notes_research_space_id"), "research_notes", ["research_space_id"], unique=False)
    op.create_foreign_key(
        "fk_research_notes_research_space_id_research_spaces",
        "research_notes",
        "research_spaces",
        ["research_space_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("research_notes", "project_id", existing_type=sa.UUID(), nullable=True)

    op.alter_column("research_chunks", "project_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.alter_column("research_chunks", "project_id", existing_type=sa.UUID(), nullable=False)

    op.alter_column("research_notes", "project_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("fk_research_notes_research_space_id_research_spaces", "research_notes", type_="foreignkey")
    op.drop_index(op.f("ix_research_notes_research_space_id"), table_name="research_notes")
    op.drop_column("research_notes", "research_space_id")

    op.alter_column("research_references", "project_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("fk_research_references_research_space_id_research_spaces", "research_references", type_="foreignkey")
    op.drop_index(op.f("ix_research_references_research_space_id"), table_name="research_references")
    op.drop_column("research_references", "research_space_id")

    op.alter_column("research_collections", "project_id", existing_type=sa.UUID(), nullable=False)
    op.drop_constraint("fk_research_collections_research_space_id_research_spaces", "research_collections", type_="foreignkey")
    op.drop_index(op.f("ix_research_collections_research_space_id"), table_name="research_collections")
    op.drop_column("research_collections", "research_space_id")
