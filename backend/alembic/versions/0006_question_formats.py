"""questions: choice formats with options

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column("format", sa.String(length=10), server_default="free", nullable=False),
    )
    for name in ("options", "correct_options", "selected_options"):
        op.add_column("questions", sa.Column(name, postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    for name in ("selected_options", "correct_options", "options", "format"):
        op.drop_column("questions", name)
