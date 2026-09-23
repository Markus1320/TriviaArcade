"""SQLAlchemy models for PostgreSQL. Every change needs an Alembic migration."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Identity, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class LLMCall(Base):
    """One generator or judge call, kept for reviewing question quality and verdicts."""

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    purpose: Mapped[str] = mapped_column(String(20), index=True)
    model: Mapped[str] = mapped_column(String(200))
    attempt: Mapped[int] = mapped_column(SmallInteger)
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    raw_output: Mapped[str | None] = mapped_column(Text)
    parsed: Mapped[Any | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[int] = mapped_column(Integer)
