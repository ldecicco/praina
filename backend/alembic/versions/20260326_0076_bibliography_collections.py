"""bibliography collections

Revision ID: 20260326_0076
Revises: 20260326_0075
Create Date: 2026-03-26 21:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260326_0076"
down_revision = "20260326_0075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bibliography_collections",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "visibility",
            postgresql.ENUM("private", "shared", name="bibliography_visibility", create_type=False),
            nullable=False,
            server_default="private",
        ),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["owner_user_id"], ["user_accounts.id"], ondelete="CASCADE", name="fk_biblio_col_owner"),
        sa.PrimaryKeyConstraint("id", name="pk_bibliography_collections"),
    )
    op.create_index("ix_biblio_col_owner", "bibliography_collections", ["owner_user_id"], unique=False)
    op.create_index("ix_biblio_col_visibility", "bibliography_collections", ["visibility"], unique=False)

    op.create_table(
        "bibliography_collection_references",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["bibliography_collections.id"], ondelete="CASCADE", name="fk_biblio_col_ref_col"),
        sa.ForeignKeyConstraint(["reference_id"], ["bibliography_references.id"], ondelete="CASCADE", name="fk_biblio_col_ref_ref"),
        sa.PrimaryKeyConstraint("collection_id", "reference_id", name="pk_biblio_collection_references"),
    )


def downgrade() -> None:
    op.drop_table("bibliography_collection_references")
    op.drop_index("ix_biblio_col_visibility", table_name="bibliography_collections")
    op.drop_index("ix_biblio_col_owner", table_name="bibliography_collections")
    op.drop_table("bibliography_collections")
