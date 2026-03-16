"""coordinator partner, partner type/country, google docs linking

Revision ID: 20260310_0029
Revises: 20260310_0028
Create Date: 2026-03-10 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260310_0029"
down_revision = "20260310_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "coordinator_partner_id",
            sa.UUID(),
            sa.ForeignKey("partner_organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "principal_investigator_id",
            sa.UUID(),
            sa.ForeignKey("team_members.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "partner_organizations",
        sa.Column("partner_type", sa.String(32), nullable=False, server_default="beneficiary"),
    )
    op.add_column(
        "partner_organizations",
        sa.Column("country", sa.String(2), nullable=True),
    )
    op.add_column(
        "project_documents",
        sa.Column("source_url", sa.String(512), nullable=True),
    )
    op.add_column(
        "project_documents",
        sa.Column("source_type", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_documents", "source_type")
    op.drop_column("project_documents", "source_url")
    op.drop_column("partner_organizations", "country")
    op.drop_column("partner_organizations", "partner_type")
    op.drop_column("projects", "principal_investigator_id")
    op.drop_column("projects", "coordinator_partner_id")
