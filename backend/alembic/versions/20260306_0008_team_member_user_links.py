"""link team members to user accounts and relax global email uniqueness

Revision ID: 20260306_0008
Revises: 20260306_0007
Create Date: 2026-03-06 09:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260306_0008"
down_revision = "20260306_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("team_members", sa.Column("user_account_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_team_members_user_account_id",
        "team_members",
        "user_accounts",
        ["user_account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_team_members_user_account_id", "team_members", ["user_account_id"], unique=False)

    op.drop_index("ix_team_members_email", table_name="team_members")
    op.execute("ALTER TABLE team_members DROP CONSTRAINT IF EXISTS team_members_email_key")
    op.execute("ALTER TABLE team_members DROP CONSTRAINT IF EXISTS uq_team_members_email_global")
    op.create_index("ix_team_members_email", "team_members", ["email"], unique=False)
    op.create_unique_constraint("uq_team_member_project_email", "team_members", ["project_id", "email"])


def downgrade() -> None:
    op.drop_constraint("uq_team_member_project_email", "team_members", type_="unique")
    op.drop_index("ix_team_members_email", table_name="team_members")
    op.create_unique_constraint("uq_team_members_email_global", "team_members", ["email"])
    op.create_index("ix_team_members_email", "team_members", ["email"], unique=True)

    op.drop_index("ix_team_members_user_account_id", table_name="team_members")
    op.drop_constraint("fk_team_members_user_account_id", "team_members", type_="foreignkey")
    op.drop_column("team_members", "user_account_id")
