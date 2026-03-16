"""add wp link tables for milestones and deliverables, relax legacy deliverable wp column

Revision ID: 20260306_0011
Revises: 20260306_0010
Create Date: 2026-03-06 19:15:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260306_0011"
down_revision = "20260306_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deliverable_wps (
            deliverable_id UUID NOT NULL REFERENCES deliverables(id) ON DELETE CASCADE,
            wp_id UUID NOT NULL REFERENCES work_packages(id) ON DELETE CASCADE,
            PRIMARY KEY (deliverable_id, wp_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_deliverable_wps_wp_id ON deliverable_wps (wp_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS milestone_wps (
            milestone_id UUID NOT NULL REFERENCES milestones(id) ON DELETE CASCADE,
            wp_id UUID NOT NULL REFERENCES work_packages(id) ON DELETE CASCADE,
            PRIMARY KEY (milestone_id, wp_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_milestone_wps_wp_id ON milestone_wps (wp_id)")

    # Backfill links from legacy deliverables.wp_id data, if present.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'deliverables'
              AND column_name = 'wp_id'
          ) THEN
            INSERT INTO deliverable_wps (deliverable_id, wp_id)
            SELECT d.id, d.wp_id
            FROM deliverables d
            WHERE d.wp_id IS NOT NULL
            ON CONFLICT DO NOTHING;
          END IF;
        END $$;
        """
    )

    # Current app model stores deliverable->WP relation in deliverable_wps.
    # Keep legacy deliverables.wp_id column nullable for backward compatibility.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'deliverables'
              AND column_name = 'wp_id'
          ) THEN
            ALTER TABLE deliverables ALTER COLUMN wp_id DROP NOT NULL;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Best-effort backfill into legacy column before dropping relation table.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'deliverables'
              AND column_name = 'wp_id'
          ) THEN
            UPDATE deliverables d
            SET wp_id = src.wp_id
            FROM (
              SELECT deliverable_id, MIN(wp_id) AS wp_id
              FROM deliverable_wps
              GROUP BY deliverable_id
            ) src
            WHERE d.id = src.deliverable_id
              AND d.wp_id IS NULL;
          END IF;
        END $$;
        """
    )

    op.execute("DROP TABLE IF EXISTS milestone_wps")
    op.execute("DROP TABLE IF EXISTS deliverable_wps")
