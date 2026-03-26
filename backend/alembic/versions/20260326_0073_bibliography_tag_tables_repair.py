"""repair bibliography tag tables after 0072 rewrite

Revision ID: 20260326_0073
Revises: 20260326_0072
Create Date: 2026-03-26 17:15:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260326_0073"
down_revision = "20260326_0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = set(inspector.get_table_names())
    if "bibliography_tags" not in existing_tables:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS bibliography_tags (
                label VARCHAR(64) NOT NULL,
                slug VARCHAR(64) NOT NULL,
                id UUID NOT NULL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_bibliography_tags_label UNIQUE (label),
                CONSTRAINT uq_bibliography_tags_slug UNIQUE (slug)
            )
            """
        )
        op.execute("CREATE INDEX IF NOT EXISTS ix_biblio_tags_label ON bibliography_tags (label)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_biblio_tags_slug ON bibliography_tags (slug)")

    if "bibliography_reference_tags" not in existing_tables:
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS bibliography_reference_tags (
                reference_id UUID NOT NULL,
                tag_id UUID NOT NULL,
                CONSTRAINT pk_biblio_ref_tags PRIMARY KEY (reference_id, tag_id),
                CONSTRAINT fk_biblio_ref_tags_ref FOREIGN KEY (reference_id) REFERENCES bibliography_references (id) ON DELETE CASCADE,
                CONSTRAINT fk_biblio_ref_tags_tag FOREIGN KEY (tag_id) REFERENCES bibliography_tags (id) ON DELETE CASCADE
            )
            """
        )

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
    pass
