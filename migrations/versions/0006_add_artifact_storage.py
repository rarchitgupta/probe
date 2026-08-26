"""Add artifact storage provider.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "run_artifacts",
        sa.Column("storage", sa.String(16), nullable=False, server_default="local"),
    )


def downgrade() -> None:
    op.drop_column("run_artifacts", "storage")
