"""normalize bibliography tags into dedicated tables

Revision ID: 20260326_0072
Revises: 20260325_0071
Create Date: 2026-03-26 10:40:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260326_0072"
down_revision = "20260325_0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bibliography_tags",
        sa.Column("label", sa.String(length=64), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("label", name="uq_bibliography_tags_label"),
        sa.UniqueConstraint("slug", name="uq_bibliography_tags_slug"),
    )
    op.create_index("ix_biblio_tags_label", "bibliography_tags", ["label"], unique=False)
    op.create_index("ix_biblio_tags_slug", "bibliography_tags", ["slug"], unique=False)

    op.create_table(
        "bibliography_reference_tags",
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tag_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["reference_id"], ["bibliography_references.id"], ondelete="CASCADE", name="fk_biblio_ref_tags_ref"),
        sa.ForeignKeyConstraint(["tag_id"], ["bibliography_tags.id"], ondelete="CASCADE", name="fk_biblio_ref_tags_tag"),
        sa.PrimaryKeyConstraint("reference_id", "tag_id", name="pk_biblio_ref_tags"),
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("bibliography_references")}
    if "tags" in columns:
        op.execute(
            """
            INSERT INTO bibliography_tags (id, label, slug, created_at, updated_at)
            SELECT gen_random_uuid(), src.label, src.slug, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            FROM (
                SELECT DISTINCT
                    trim(value) AS label,
                    regexp_replace(lower(trim(value)), '[^a-z0-9]+', '-', 'g') AS slug
                FROM bibliography_references,
                LATERAL jsonb_array_elements_text(tags) AS value
                WHERE trim(value) <> ''
            ) AS src
            ON CONFLICT (label) DO NOTHING
            """
        )
        op.execute(
            """
            INSERT INTO bibliography_reference_tags (reference_id, tag_id)
            SELECT DISTINCT br.id, bt.id
            FROM bibliography_references AS br
            JOIN LATERAL jsonb_array_elements_text(br.tags) AS value ON TRUE
            JOIN bibliography_tags AS bt ON bt.label = trim(value)
            WHERE trim(value) <> ''
            ON CONFLICT DO NOTHING
            """
        )
        op.drop_column("bibliography_references", "tags")


def downgrade() -> None:
    op.add_column(
        "bibliography_references",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.execute(
        """
        UPDATE bibliography_references AS br
        SET tags = COALESCE(tag_rows.tags, '[]'::jsonb)
        FROM (
            SELECT brt.reference_id, jsonb_agg(bt.label ORDER BY lower(bt.label)) AS tags
            FROM bibliography_reference_tags AS brt
            JOIN bibliography_tags AS bt ON bt.id = brt.tag_id
            GROUP BY brt.reference_id
        ) AS tag_rows
        WHERE br.id = tag_rows.reference_id
        """
    )
    op.alter_column("bibliography_references", "tags", server_default=None)
    op.drop_table("bibliography_reference_tags")
    op.drop_index("ix_biblio_tags_slug", table_name="bibliography_tags")
    op.drop_index("ix_biblio_tags_label", table_name="bibliography_tags")
    op.drop_table("bibliography_tags")
