"""questions: shown_at and timed_out for the time limit

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("shown_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "questions",
        sa.Column("timed_out", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("questions", "timed_out")
    op.drop_column("questions", "shown_at")
