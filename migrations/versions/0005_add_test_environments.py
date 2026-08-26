"""Add reusable test environments.

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "test_environments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("viewport_width", sa.Integer(), nullable=False),
        sa.Column("viewport_height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    with op.batch_alter_table("task_runs") as batch:
        batch.add_column(sa.Column("environment_id", sa.String(32)))
        batch.create_foreign_key(
            "fk_task_runs_environment_id",
            "test_environments",
            ["environment_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("task_runs") as batch:
        batch.drop_constraint("fk_task_runs_environment_id", type_="foreignkey")
        batch.drop_column("environment_id")
    op.drop_table("test_environments")
