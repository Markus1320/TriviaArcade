"""questions: the pool record a question came from

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("questions", sa.Column("pool_question_id", sa.String(12), nullable=True))
    op.create_index("ix_questions_pool_question_id", "questions", ["pool_question_id"])


def downgrade() -> None:
    op.drop_index("ix_questions_pool_question_id", table_name="questions")
    op.drop_column("questions", "pool_question_id")
