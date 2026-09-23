"""create players, runs and questions; link llm_calls to runs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("handle", sa.String(8), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("handle", name="players_handle_key"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("streak", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("player_id", sa.BigInteger(), sa.ForeignKey("players.id"), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('active', 'over')", name="ck_runs_status"),
    )
    op.create_index("ix_runs_player_id", "runs", ["player_id"])
    op.create_index("ix_runs_leaderboard", "runs", ["streak", "ended_at"])
    op.create_table(
        "questions",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("start_node_id", sa.String(20), nullable=False),
        sa.Column("facts", sa.Text(), nullable=False),
        sa.Column("text", sa.String(300), nullable=False),
        sa.Column("expected_answer", sa.String(200), nullable=False),
        sa.Column("accepted_answers", JSONB(), nullable=False),
        sa.Column("numeric_range", JSONB(), nullable=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("player_answer", sa.String(200), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "position", name="uq_questions_run_position"),
    )
    op.create_index("ix_questions_run_id", "questions", ["run_id"])
    op.add_column(
        "llm_calls",
        sa.Column(
            "run_id", sa.Uuid(), sa.ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_llm_calls_run_id", "llm_calls", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_llm_calls_run_id", table_name="llm_calls")
    op.drop_column("llm_calls", "run_id")
    op.drop_index("ix_questions_run_id", table_name="questions")
    op.drop_table("questions")
    op.drop_index("ix_runs_leaderboard", table_name="runs")
    op.drop_index("ix_runs_player_id", table_name="runs")
    op.drop_table("runs")
    op.drop_table("players")
