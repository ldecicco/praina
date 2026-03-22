"""simplify teaching progress reports

Revision ID: 20260321_0057
Revises: 20260321_0056
Create Date: 2026-03-21 23:15:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "20260321_0057"
down_revision = "20260321_0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teaching_progress_reports", sa.Column("report_date", sa.Date(), nullable=True))
    op.add_column("teaching_progress_reports", sa.Column("work_done_markdown", sa.Text(), nullable=False, server_default=""))
    op.add_column("teaching_progress_reports", sa.Column("next_steps_markdown", sa.Text(), nullable=False, server_default=""))
    op.create_index("ix_teaching_progress_reports_report_date", "teaching_progress_reports", ["report_date"])

    op.add_column("teaching_project_blockers", sa.Column("source_report_id", UUID(as_uuid=True), nullable=True))
    op.add_column("teaching_project_blockers", sa.Column("last_report_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_teaching_project_blockers_source_report_id", "teaching_project_blockers", ["source_report_id"])
    op.create_index("ix_teaching_project_blockers_last_report_id", "teaching_project_blockers", ["last_report_id"])
    op.create_foreign_key(
        "fk_teaching_project_blockers_source_report_id",
        "teaching_project_blockers",
        "teaching_progress_reports",
        ["source_report_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_teaching_project_blockers_last_report_id",
        "teaching_project_blockers",
        "teaching_progress_reports",
        ["last_report_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE teaching_progress_reports
        SET report_date = COALESCE(period_end, period_start, DATE(created_at)),
            work_done_markdown = COALESCE(
              NULLIF(summary_markdown, ''),
              CASE
                WHEN jsonb_array_length(COALESCE(completed_work, '[]'::jsonb)) > 0
                THEN array_to_string(ARRAY(SELECT '- ' || value FROM jsonb_array_elements_text(COALESCE(completed_work, '[]'::jsonb)) AS value), E'\n')
                ELSE ''
              END
            ),
            next_steps_markdown = CASE
              WHEN jsonb_array_length(COALESCE(next_steps, '[]'::jsonb)) > 0
              THEN array_to_string(ARRAY(SELECT '- ' || value FROM jsonb_array_elements_text(COALESCE(next_steps, '[]'::jsonb)) AS value), E'\n')
              ELSE ''
            END
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_teaching_project_blockers_last_report_id", "teaching_project_blockers", type_="foreignkey")
    op.drop_constraint("fk_teaching_project_blockers_source_report_id", "teaching_project_blockers", type_="foreignkey")
    op.drop_index("ix_teaching_project_blockers_last_report_id", table_name="teaching_project_blockers")
    op.drop_index("ix_teaching_project_blockers_source_report_id", table_name="teaching_project_blockers")
    op.drop_column("teaching_project_blockers", "last_report_id")
    op.drop_column("teaching_project_blockers", "source_report_id")

    op.drop_index("ix_teaching_progress_reports_report_date", table_name="teaching_progress_reports")
    op.drop_column("teaching_progress_reports", "next_steps_markdown")
    op.drop_column("teaching_progress_reports", "work_done_markdown")
    op.drop_column("teaching_progress_reports", "report_date")
