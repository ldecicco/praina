"""normalize legacy bot user email

Revision ID: 20260306_0010
Revises: 20260306_0009
Create Date: 2026-03-06 18:40:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260306_0010"
down_revision = "20260306_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE user_accounts legacy
        SET email = 'project-bot@agenticpm.local'
        WHERE legacy.email = 'project-bot@local'
          AND NOT EXISTS (
            SELECT 1
            FROM user_accounts current
            WHERE current.email = 'project-bot@agenticpm.local'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE user_accounts
        SET email = 'project-bot@local'
        WHERE email = 'project-bot@agenticpm.local'
          AND display_name = 'Project Bot'
        """
    )
