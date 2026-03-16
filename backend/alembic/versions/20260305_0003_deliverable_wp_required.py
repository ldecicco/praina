"""deliverable must belong to a work package

Revision ID: 20260305_0003
Revises: 20260305_0002
Create Date: 2026-03-05 22:20:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260305_0003"
down_revision = "20260305_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM deliverables WHERE wp_id IS NULL")
    op.execute("ALTER TABLE deliverables DROP CONSTRAINT IF EXISTS deliverables_wp_id_fkey")
    op.execute("ALTER TABLE deliverables ALTER COLUMN wp_id SET NOT NULL")
    op.execute(
        """
        ALTER TABLE deliverables
        ADD CONSTRAINT deliverables_wp_id_fkey
        FOREIGN KEY (wp_id) REFERENCES work_packages(id) ON DELETE CASCADE
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE deliverables DROP CONSTRAINT IF EXISTS deliverables_wp_id_fkey")
    op.execute("ALTER TABLE deliverables ALTER COLUMN wp_id DROP NOT NULL")
    op.execute(
        """
        ALTER TABLE deliverables
        ADD CONSTRAINT deliverables_wp_id_fkey
        FOREIGN KEY (wp_id) REFERENCES work_packages(id) ON DELETE SET NULL
        """
    )

