"""Create runs and events.

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_STATUSES = "'queued', 'running', 'passed', 'failed', 'blocked', 'error', 'cancelled'"


def upgrade() -> None:
    timestamp = sa.DateTime(timezone=True)
    op.create_table(
        "task_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("start_url", sa.Text(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("started_at", timestamp),
        sa.Column("finished_at", timestamp),
        sa.Column("final_url", sa.Text()),
        sa.Column("http_status", sa.Integer()),
        sa.Column("summary", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("artifact_directory", sa.Text()),
        sa.Column("input_tokens", sa.Integer()),
        sa.Column("output_tokens", sa.Integer()),
        sa.Column("cache_read_tokens", sa.Integer()),
        sa.Column("request_count", sa.Integer()),
        sa.Column("tool_call_count", sa.Integer()),
        sa.Column("cost", sa.Numeric(18, 10)),
        sa.CheckConstraint(f"status IN ({RUN_STATUSES})", name="run_status"),
    )
    op.create_index("ix_task_runs_created", "task_runs", ["created_at", "id"])
    op.create_index(
        "ix_task_runs_status_created",
        "task_runs",
        ["status", "created_at", "id"],
    )
    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            sa.Text(),
            sa.ForeignKey("task_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(9), nullable=False),
        sa.Column("created_at", timestamp, nullable=False),
        sa.Column("status", sa.String(9)),
        sa.Column("action", sa.String(32)),
        sa.Column("element", sa.Text()),
        sa.Column("success", sa.Boolean()),
        sa.Column("message", sa.Text()),
        sa.CheckConstraint(
            "kind IN ('status', 'action', 'assertion')",
            name="run_event_kind",
        ),
        sa.CheckConstraint(
            f"status IS NULL OR status IN ({RUN_STATUSES})", name="run_status"
        ),
    )
    op.create_index("ix_run_events_run_id_id", "run_events", ["run_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_run_events_run_id_id", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index("ix_task_runs_status_created", table_name="task_runs")
    op.drop_index("ix_task_runs_created", table_name="task_runs")
    op.drop_table("task_runs")
