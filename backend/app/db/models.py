"""SQLAlchemy models for PostgreSQL. Every change needs an Alembic migration."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSONB on PostgreSQL; plain JSON elsewhere (the tests use SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")
# BIGINT on PostgreSQL; SQLite only auto-increments INTEGER primary keys.
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")

RUN_ACTIVE = "active"
RUN_OVER = "over"


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(BigIntPK, Identity(), primary_key=True)
    handle: Mapped[str] = mapped_column(String(8), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Run(Base):
    """One game from START to the first wrong answer."""

    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(f"status IN ('{RUN_ACTIVE}', '{RUN_OVER}')", name="ck_runs_status"),
        Index("ix_runs_leaderboard", "streak", "ended_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(10), default=RUN_ACTIVE)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    player: Mapped[Player | None] = relationship()
    questions: Mapped[list["Question"]] = relationship(
        back_populates="run", order_by="Question.position"
    )


class Question(Base):
    """A question asked in a run, with the server side answers and the verdict."""

    __tablename__ = "questions"
    __table_args__ = (UniqueConstraint("run_id", "position", name="uq_questions_run_position"),)

    id: Mapped[int] = mapped_column(BigIntPK, Identity(), primary_key=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(SmallInteger)
    start_node_id: Mapped[str] = mapped_column(String(20))
    facts: Mapped[str] = mapped_column(Text)
    text: Mapped[str] = mapped_column(String(300))
    expected_answer: Mapped[str] = mapped_column(String(200))
    accepted_answers: Mapped[list[str]] = mapped_column(JSONType)
    numeric_range: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    asked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    player_answer: Mapped[str | None] = mapped_column(String(200))
    correct: Mapped[bool | None] = mapped_column(Boolean)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[Run] = relationship(back_populates="questions")


class LLMCall(Base):
    """One generator or judge call, kept for reviewing question quality and verdicts."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigIntPK, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    purpose: Mapped[str] = mapped_column(String(20), index=True)
    model: Mapped[str] = mapped_column(String(200))
    attempt: Mapped[int] = mapped_column(SmallInteger)
    request: Mapped[dict[str, Any]] = mapped_column(JSONType)
    raw_output: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[Any | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), index=True
    )
