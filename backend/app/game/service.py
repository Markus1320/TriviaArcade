"""Server side run lifecycle: start, ask, judge, game over.

All game state lives in PostgreSQL. The browser only gets the run ID, question texts and
results; expected answers leave the server only after the run is over.

Each public method runs in its own transaction and locks the run row, so two parallel
requests for the same run cannot both generate a question or both judge an answer.
"""

import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RUN_OVER, Question, Run
from app.game.rules import Progress, apply_verdict
from app.graph.model import QuestionSeed
from app.graph.walk import NoQuestionSeedError
from app.llm.facts import format_seed
from app.llm.generator import GeneratedQuestion, NumericRange, QuestionGenerationError
from app.llm.judge import JudgeInput, JudgeUnavailableError, sanitize_answer


class SeedSource(Protocol):
    def walk(self, exclude_start_ids: Collection[str] = ()) -> QuestionSeed: ...


class QuestionSource(Protocol):
    def generate(
        self, seed: QuestionSeed, *, run_id: uuid.UUID | None = None
    ) -> GeneratedQuestion: ...


class AnswerChecker(Protocol):
    def judge(
        self, item: JudgeInput, player_answer: str, *, run_id: uuid.UUID | None = None
    ) -> bool: ...


class GameError(Exception):
    """Base class for errors the API turns into HTTP responses."""


class RunNotFoundError(GameError):
    pass


class RunOverError(GameError):
    pass


class NoOpenQuestionError(GameError):
    pass


class InvalidAnswerError(GameError):
    pass


class QuestionUnavailableError(GameError):
    """No question could be created right now; the run continues."""


class JudgePausedError(GameError):
    """The judge failed technically. The run is paused, not ended; the answer can be resent."""


@dataclass(frozen=True)
class QuestionView:
    question_id: int
    number: int
    text: str
    streak: int


@dataclass(frozen=True)
class AnswerResult:
    correct: bool
    streak: int
    game_over: bool
    # Only filled when the run is over: the correct answer to the last question.
    expected_answer: str | None


@dataclass(frozen=True)
class RunView:
    run_id: uuid.UUID
    over: bool
    streak: int
    open_question: QuestionView | None
    last_expected_answer: str | None
    claimed_by: str | None


def utc_now() -> datetime:
    return datetime.now(UTC)


class GameService:
    def __init__(
        self,
        session: Session,
        seeds: SeedSource,
        generator: QuestionSource,
        judge: AnswerChecker,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._session = session
        self._seeds = seeds
        self._generator = generator
        self._judge = judge
        self._clock = clock

    def start_run(self) -> uuid.UUID:
        with self._session.begin():
            run = Run(started_at=self._clock(), status="active", streak=0)
            self._session.add(run)
            self._session.flush()
            return run.id

    def get_run(self, run_id: uuid.UUID) -> RunView:
        with self._session.begin():
            run = self._load_run(run_id, lock=False)
            open_question = _open_question(run)
            last = run.questions[-1] if run.questions else None
            return RunView(
                run_id=run.id,
                over=run.status == RUN_OVER,
                streak=run.streak,
                open_question=_view(open_question, run) if open_question else None,
                last_expected_answer=last.expected_answer
                if run.status == RUN_OVER and last
                else None,
                claimed_by=run.player.handle if run.player else None,
            )

    def next_question(self, run_id: uuid.UUID) -> QuestionView:
        """Return the open question, or create the next one.

        Asking again before answering returns the same question, so a page reload
        cannot be used to skip a question.
        """
        with self._session.begin():
            run = self._load_run(run_id, lock=True)
            if run.status == RUN_OVER:
                raise RunOverError("the run is over")
            open_question = _open_question(run)
            if open_question is not None:
                return _view(open_question, run)

            used_starts = {question.start_node_id for question in run.questions}
            try:
                seed = self._seeds.walk(exclude_start_ids=used_starts)
                generated = self._generator.generate(seed, run_id=run.id)
            except (NoQuestionSeedError, QuestionGenerationError) as error:
                raise QuestionUnavailableError(str(error)) from error

            question = Question(
                run=run,
                position=len(run.questions) + 1,
                start_node_id=seed.start.wikidata_id,
                facts=format_seed(seed),
                text=generated.question,
                expected_answer=generated.expected_answer,
                accepted_answers=generated.accepted_answers,
                numeric_range=(
                    generated.numeric_range.model_dump() if generated.numeric_range else None
                ),
                asked_at=self._clock(),
            )
            self._session.add(question)
            self._session.flush()
            return _view(question, run)

    def answer(self, run_id: uuid.UUID, player_answer: str) -> AnswerResult:
        with self._session.begin():
            run = self._load_run(run_id, lock=True)
            if run.status == RUN_OVER:
                raise RunOverError("the run is over")
            question = _open_question(run)
            if question is None:
                raise NoOpenQuestionError("there is no open question")
            answer = sanitize_answer(player_answer)
            if not answer:
                raise InvalidAnswerError("the answer is empty")

            item = JudgeInput(
                question=question.text,
                expected_answer=question.expected_answer,
                accepted_answers=tuple(question.accepted_answers),
                numeric_range=(
                    NumericRange.model_validate(question.numeric_range)
                    if question.numeric_range
                    else None
                ),
            )
            try:
                correct = self._judge.judge(item, answer, run_id=run.id)
            except JudgeUnavailableError as error:
                # Nothing is written: the question stays open and the run continues.
                raise JudgePausedError(str(error)) from error

            progress = apply_verdict(Progress(streak=run.streak), correct)
            now = self._clock()
            question.player_answer = answer
            question.correct = correct
            question.answered_at = now
            run.streak = progress.streak
            if progress.over:
                run.status = RUN_OVER
                run.ended_at = now
            return AnswerResult(
                correct=correct,
                streak=progress.streak,
                game_over=progress.over,
                expected_answer=question.expected_answer if progress.over else None,
            )

    def _load_run(self, run_id: uuid.UUID, *, lock: bool) -> Run:
        query = select(Run).where(Run.id == run_id)
        if lock:
            # FOR NO KEY UPDATE: still lets the call log insert rows referencing this run.
            query = query.with_for_update(key_share=True)
        run = self._session.scalars(query).one_or_none()
        if run is None:
            raise RunNotFoundError(f"run {run_id} not found")
        return run


def _open_question(run: Run) -> Question | None:
    if run.questions and run.questions[-1].correct is None:
        return run.questions[-1]
    return None


def _view(question: Question, run: Run) -> QuestionView:
    return QuestionView(
        question_id=question.id, number=question.position, text=question.text, streak=run.streak
    )
