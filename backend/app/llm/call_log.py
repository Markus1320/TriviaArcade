"""Logging of every LLM call into PostgreSQL."""

import logging
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal, Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import LLMCall

logger = logging.getLogger(__name__)

Purpose = Literal["generate", "judge"]


@dataclass(frozen=True)
class LLMCallRecord:
    purpose: Purpose
    model: str
    attempt: int
    request: dict[str, Any]
    raw_output: str | None
    parsed: Any
    error: str | None
    latency_ms: int
    run_id: uuid.UUID | None = None


class CallLogger(Protocol):
    def log(self, record: LLMCallRecord) -> None: ...


class SqlCallLogger:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def log(self, record: LLMCallRecord) -> None:
        # A logging failure must not break the game; it is reported and skipped.
        try:
            with self._session_factory.begin() as session:
                session.add(LLMCall(**asdict(record)))
        except Exception:
            logger.exception("Could not write LLM call log (%s)", record.purpose)


class NullCallLogger:
    def log(self, record: LLMCallRecord) -> None:
        return None
