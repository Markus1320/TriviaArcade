"""Server side run lifecycle: start, ask, judge, game over.

All game state lives in PostgreSQL. The browser only gets the run ID, question texts and
results; expected answers leave the server only after the run is over.

Each public method runs in its own transaction and locks the run row, so two parallel
requests for the same run cannot both generate a question or both judge an answer.

Time limit: generating a question (also when prefetched) does not start the clock;
start_question does, when the browser shows the question. The deadline is checked when an
answer arrives, before judging. A late answer ends the run without asking the judge.
"""

import uuid
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RUN_OVER, Question, Run
from app.game.rules import Progress, answer_in_time, apply_verdict, seconds_left
from app.graph.model import QuestionSeed
from app.graph.walk import NoQuestionSeedError
from app.llm.facts import format_seed
from app.llm.generator import GeneratedQuestion, QuestionGenerationError
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
    # None when the time limit is off.
    time_limit_seconds: int | None
    # None until the question has been started (shown), or when the time limit is off.
    seconds_left: float | None


@dataclass(frozen=True)
class AnswerResult:
    correct: bool
    streak: int
    game_over: bool
    timed_out: bool
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


def _as_utc(value: datetime) -> datetime:
    # SQLite returns naive datetimes; PostgreSQL returns aware ones.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class GameService:
    def __init__(
        self,
        session: Session,
        seeds: SeedSource,
        generator: QuestionSource,
        judge: AnswerChecker,
        clock: Callable[[], datetime] = utc_now,
        answer_time_seconds: int = 45,
    ) -> None:
        self._session = session
        self._seeds = seeds
        self._generator = generator
        self._judge = judge
        self._clock = clock
        # 0 turns the time limit off.
        self._time_limit = answer_time_seconds or None

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
                open_question=self._view(open_question, run) if open_question else None,
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
                return self._view(open_question, run)

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
                asked_at=self._clock(),
            )
            self._session.add(question)
            self._session.flush()
            return self._view(question, run)

    def start_question(self, run_id: uuid.UUID) -> QuestionView:
        """Start the clock on the open question. Calling it again keeps the running clock."""
        with self._session.begin():
            run = self._load_run(run_id, lock=True)
            question = self._open_question_or_raise(run)
            if question.shown_at is None:
                question.shown_at = self._clock()
            return self._view(question, run)

    def answer(self, run_id: uuid.UUID, player_answer: str) -> AnswerResult:
        judge_error: JudgeUnavailableError | None = None
        with self._session.begin():
            run = self._load_run(run_id, lock=True)
            question = self._open_question_or_raise(run)
            answer = sanitize_answer(player_answer)
            if not answer:
                raise InvalidAnswerError("the answer is empty")
            received_at = self._clock()
            if question.shown_at is None:
                question.shown_at = received_at
            if not self._in_time(question, received_at):
                return self._finish(run, question, answer, correct=False, timed_out=True)

            item = JudgeInput(
                question=question.text,
                expected_answer=question.expected_answer,
                accepted_answers=tuple(question.accepted_answers),
            )
            try:
                correct = self._judge.judge(item, answer, run_id=run.id)
            except JudgeUnavailableError as error:
                # No verdict is written: the question stays open and the run continues.
                # The player gets a fresh time limit; a technical failure must not cost time.
                question.shown_at = self._clock()
                judge_error = error
            else:
                return self._finish(run, question, answer, correct=correct, timed_out=False)
        raise JudgePausedError(str(judge_error)) from judge_error

    def time_out(self, run_id: uuid.UUID) -> AnswerResult:
        """End the run because the time for the open question ran out without an answer.

        Sent by the browser when its countdown ends. It only ever ends the caller's own run,
        so the server does not need to check the deadline here.
        """
        with self._session.begin():
            run = self._load_run(run_id, lock=True)
            question = self._open_question_or_raise(run)
            return self._finish(run, question, None, correct=False, timed_out=True)

    def _finish(
        self,
        run: Run,
        question: Question,
        answer: str | None,
        *,
        correct: bool,
        timed_out: bool,
    ) -> AnswerResult:
        progress = apply_verdict(Progress(streak=run.streak), correct)
        now = self._clock()
        question.player_answer = answer
        question.correct = correct
        question.timed_out = timed_out
        question.answered_at = now
        run.streak = progress.streak
        if progress.over:
            run.status = RUN_OVER
            run.ended_at = now
        return AnswerResult(
            correct=correct,
            streak=progress.streak,
            game_over=progress.over,
            timed_out=timed_out,
            expected_answer=question.expected_answer if progress.over else None,
        )

    def _in_time(self, question: Question, received_at: datetime) -> bool:
        if self._time_limit is None or question.shown_at is None:
            return True
        return answer_in_time(_as_utc(question.shown_at), received_at, self._time_limit)

    def _view(self, question: Question, run: Run) -> QuestionView:
        left = None
        if self._time_limit is not None and question.shown_at is not None:
            left = seconds_left(_as_utc(question.shown_at), self._clock(), self._time_limit)
        return QuestionView(
            question_id=question.id,
            number=question.position,
            text=question.text,
            streak=run.streak,
            time_limit_seconds=self._time_limit,
            seconds_left=left,
        )

    @staticmethod
    def _open_question_or_raise(run: Run) -> Question:
        if run.status == RUN_OVER:
            raise RunOverError("the run is over")
        question = _open_question(run)
        if question is None:
            raise NoOpenQuestionError("there is no open question")
        return question

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
