"""runs: 1UPs and combo; questions: skipped

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("lives", sa.SmallInteger(), server_default="0", nullable=False))
    op.add_column("runs", sa.Column("combo", sa.SmallInteger(), server_default="0", nullable=False))
    op.add_column(
        "questions",
        sa.Column("skipped", sa.Boolean(), server_default=sa.false(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("questions", "skipped")
    op.drop_column("runs", "combo")
    op.drop_column("runs", "lives")
