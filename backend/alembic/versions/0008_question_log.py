"""questions: generator model, prompt and notes for the question log

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("generator_model", sa.String(length=200), nullable=True))
    op.add_column("questions", sa.Column("prompt", sa.Text(), nullable=True))
    op.add_column("questions", sa.Column("notes", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("questions", "notes")
    op.drop_column("questions", "prompt")
    op.drop_column("questions", "generator_model")
