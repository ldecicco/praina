"""central bibliography

Revision ID: 20260325_0068
Revises: 20260325_0067
Create Date: 2026-03-25 21:10:00.000000
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260325_0068"
down_revision = "20260325_0067"
branch_labels = None
depends_on = None


bibliography_visibility = postgresql.ENUM(
    "private",
    "shared",
    name="bibliography_visibility",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            CREATE TYPE bibliography_visibility AS ENUM ('private', 'shared');
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    op.create_table(
        "bibliography_references",
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("venue", sa.String(length=512), nullable=True),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("bibtex_raw", sa.Text(), nullable=True),
        sa.Column("attachment_path", sa.String(length=512), nullable=True),
        sa.Column("attachment_filename", sa.String(length=255), nullable=True),
        sa.Column("attachment_mime_type", sa.String(length=255), nullable=True),
        sa.Column("visibility", bibliography_visibility, nullable=False, server_default="shared"),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["user_accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bibliography_references_created_by_user_id"), "bibliography_references", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_bibliography_references_doi"), "bibliography_references", ["doi"], unique=False)
    op.create_index(op.f("ix_bibliography_references_visibility"), "bibliography_references", ["visibility"], unique=False)

    op.add_column("research_references", sa.Column("bibliography_reference_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f("ix_research_references_bibliography_reference_id"), "research_references", ["bibliography_reference_id"], unique=False)
    op.create_foreign_key(
        "fk_research_references_bibliography_reference_id",
        "research_references",
        "bibliography_references",
        ["bibliography_reference_id"],
        ["id"],
        ondelete="SET NULL",
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    references = sa.Table(
        "research_references",
        metadata,
        sa.Column("id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(length=512)),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("year", sa.Integer()),
        sa.Column("venue", sa.String(length=512)),
        sa.Column("doi", sa.String(length=255)),
        sa.Column("url", sa.String(length=512)),
        sa.Column("abstract", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("bibliography_reference_id", postgresql.UUID(as_uuid=True)),
        sa.Column("added_by_member_id", postgresql.UUID(as_uuid=True)),
    )
    team_members = sa.Table(
        "team_members",
        metadata,
        sa.Column("id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_account_id", postgresql.UUID(as_uuid=True)),
    )
    bibliography = sa.Table(
        "bibliography_references",
        metadata,
        sa.Column("id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(length=512)),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("year", sa.Integer()),
        sa.Column("venue", sa.String(length=512)),
        sa.Column("doi", sa.String(length=255)),
        sa.Column("url", sa.String(length=512)),
        sa.Column("abstract", sa.Text()),
        sa.Column("visibility", bibliography_visibility),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    rows = bind.execute(
        sa.select(
            references.c.id,
            references.c.title,
            references.c.authors,
            references.c.year,
            references.c.venue,
            references.c.doi,
            references.c.url,
            references.c.abstract,
            references.c.created_at,
            references.c.updated_at,
            team_members.c.user_account_id,
        ).select_from(
            references.outerjoin(team_members, team_members.c.id == references.c.added_by_member_id)
        )
    ).mappings().all()

    doi_map: dict[str, uuid.UUID] = {}
    title_map: dict[str, uuid.UUID] = {}
    for row in rows:
        doi = (row["doi"] or "").strip()
        norm_title = (row["title"] or "").strip().lower()
        bibliography_id = doi_map.get(doi) if doi else None
        if bibliography_id is None and norm_title:
            bibliography_id = title_map.get(norm_title)
        if bibliography_id is None:
            bibliography_id = uuid.uuid4()
            bind.execute(
                bibliography.insert().values(
                    id=bibliography_id,
                    title=row["title"],
                    authors=row["authors"] or [],
                    year=row["year"],
                    venue=row["venue"],
                    doi=doi or None,
                    url=row["url"],
                    abstract=row["abstract"],
                    visibility="shared",
                    created_by_user_id=row["user_account_id"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
            if doi:
                doi_map[doi] = bibliography_id
            if norm_title:
                title_map[norm_title] = bibliography_id
        bind.execute(
            references.update()
            .where(references.c.id == row["id"])
            .values(bibliography_reference_id=bibliography_id)
        )


def downgrade() -> None:
    op.drop_constraint("fk_research_references_bibliography_reference_id", "research_references", type_="foreignkey")
    op.drop_index(op.f("ix_research_references_bibliography_reference_id"), table_name="research_references")
    op.drop_column("research_references", "bibliography_reference_id")

    op.drop_index(op.f("ix_bibliography_references_visibility"), table_name="bibliography_references")
    op.drop_index(op.f("ix_bibliography_references_doi"), table_name="bibliography_references")
    op.drop_index(op.f("ix_bibliography_references_created_by_user_id"), table_name="bibliography_references")
    op.drop_table("bibliography_references")
    op.execute("DROP TYPE IF EXISTS bibliography_visibility")
