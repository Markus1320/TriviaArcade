"""The public question log: recent questions of finished runs, without player data.

Only finished runs are listed, so no answer of a running game is revealed. Each question
shows whether it was answered correctly, never the player's answer or handle.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RUN_OVER, Question, Run

# Questions per request ("load more") and the most that can be seen in total.
PAGE_SIZE = 10
LOG_SIZE = 50


@dataclass(frozen=True)
class LoggedQuestion:
    id: int
    # When the run ended; questions of one run share it and are shown as a group.
    run_ended_at: datetime
    language: str
    number: int
    correct: bool
    # Skipped with a 1UP: neither right nor wrong.
    skipped: bool
    format: str
    question: str
    options: list[str]
    correct_options: list[int]
    expected_answer: str
    accepted_answers: list[str]
    explanation: str | None
    notes: dict[str, Any]
    model: str
    prompt: str


@dataclass(frozen=True)
class LogPage:
    questions: Sequence[LoggedQuestion]
    has_more: bool


class QuestionLogService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def page(self, offset: int) -> LogPage:
        """Newest runs first, and within a run the last question first."""
        limit = min(PAGE_SIZE, LOG_SIZE - offset)
        if limit <= 0:
            return LogPage((), has_more=False)
        rows = self._session.execute(
            select(Question, Run.ended_at, Run.language)
            .join(Run)
            .where(
                Run.status == RUN_OVER,
                Run.ended_at.is_not(None),
                Question.correct.is_not(None),
                # Questions from before the log have no prompt stored.
                Question.prompt.is_not(None),
            )
            .order_by(Run.ended_at.desc(), Run.id, Question.position.desc())
            .offset(offset)
            # One more than needed tells whether there is a next page.
            .limit(limit + 1)
        ).all()
        questions = [
            _logged(question, ended_at, language) for question, ended_at, language in rows[:limit]
        ]
        has_more = len(rows) > limit and offset + limit < LOG_SIZE
        return LogPage(questions, has_more)


def _logged(question: Question, ended_at: datetime, language: str) -> LoggedQuestion:
    # correct and prompt are set: page() only selects such questions.
    return LoggedQuestion(
        id=question.id,
        run_ended_at=ended_at,
        language=language,
        number=question.position,
        correct=bool(question.correct),
        skipped=question.skipped,
        format=question.format,
        question=question.text,
        options=list(question.options or ()),
        correct_options=list(question.correct_options or ()),
        expected_answer=question.expected_answer,
        accepted_answers=list(question.accepted_answers),
        explanation=question.explanation,
        notes=dict(question.notes or {}),
        model=question.generator_model or "",
        prompt=question.prompt or "",
    )
