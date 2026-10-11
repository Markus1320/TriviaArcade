"""runs: language of the questions

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("language", sa.String(length=2), server_default="en", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("runs", "language")
