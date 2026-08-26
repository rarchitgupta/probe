"""Add run artifacts.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "run_id",
            sa.Text(),
            sa.ForeignKey("task_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_run_artifacts_run_id", "run_artifacts", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_run_artifacts_run_id", table_name="run_artifacts")
    op.drop_table("run_artifacts")
