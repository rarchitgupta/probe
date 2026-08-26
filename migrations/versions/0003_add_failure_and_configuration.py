"""Add failure category and agent configuration.

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("task_runs", sa.Column("failure_category", sa.String(32)))
    op.add_column("task_runs", sa.Column("model_name", sa.String(100)))
    op.add_column("task_runs", sa.Column("prompt_version", sa.String(32)))
    op.add_column("task_runs", sa.Column("model_config_version", sa.String(32)))


def downgrade() -> None:
    op.drop_column("task_runs", "model_config_version")
    op.drop_column("task_runs", "prompt_version")
    op.drop_column("task_runs", "model_name")
    op.drop_column("task_runs", "failure_category")
