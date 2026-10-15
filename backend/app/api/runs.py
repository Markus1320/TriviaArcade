"""Run endpoints: start, question, start the clock, answer, time out, state and claim."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, model_validator

from app.api.deps import get_game_service, get_leaderboard_service
from app.game.service import AnswerResult, GameService, QuestionView
from app.languages import DEFAULT_LANGUAGE, Language
from app.leaderboard.service import LeaderboardService
from app.llm.judge import MAX_ANSWER_LENGTH

router = APIRouter(prefix="/runs", tags=["runs"])

GameDep = Annotated[GameService, Depends(get_game_service)]
LeaderboardDep = Annotated[LeaderboardService, Depends(get_leaderboard_service)]


class RunIn(BaseModel):
    language: Language = DEFAULT_LANGUAGE


class RunCreated(BaseModel):
    run_id: uuid.UUID


class QuestionOut(BaseModel):
    question_id: int
    number: int
    text: str
    format: str
    options: list[str]
    streak: int
    lives: int
    combo: int
    time_limit_seconds: int | None
    seconds_left: float | None

    @classmethod
    def from_view(cls, view: QuestionView) -> "QuestionOut":
        return cls(
            question_id=view.question_id,
            number=view.number,
            text=view.text,
            format=view.format,
            options=list(view.options),
            streak=view.streak,
            lives=view.lives,
            combo=view.combo,
            time_limit_seconds=view.time_limit_seconds,
            seconds_left=view.seconds_left,
        )


class RunState(BaseModel):
    run_id: uuid.UUID
    over: bool
    streak: int
    lives: int
    combo: int
    open_question: QuestionOut | None
    last_expected_answer: str | None
    last_explanation: str | None
    last_format: str | None
    last_options: list[str] | None
    last_correct_options: list[int] | None
    last_selected_options: list[int] | None
    claimed_by: str | None


class AnswerIn(BaseModel):
    """A typed answer for free questions, or the selected option positions for choice ones."""

    answer: str | None = Field(default=None, min_length=1, max_length=MAX_ANSWER_LENGTH)
    selected: list[int] | None = Field(default=None, min_length=1, max_length=10)

    @model_validator(mode="after")
    def exactly_one(self) -> "AnswerIn":
        if (self.answer is None) == (self.selected is None):
            raise ValueError("send either answer or selected")
        return self


class AnswerOut(BaseModel):
    correct: bool
    streak: int
    game_over: bool
    timed_out: bool
    lives: int
    combo: int
    life_earned: bool
    saved: bool
    skipped: bool
    expected_answer: str | None
    explanation: str | None
    correct_options: list[int] | None

    @classmethod
    def from_result(cls, result: AnswerResult) -> "AnswerOut":
        return cls(
            correct=result.correct,
            streak=result.streak,
            game_over=result.game_over,
            timed_out=result.timed_out,
            lives=result.lives,
            combo=result.combo,
            life_earned=result.life_earned,
            saved=result.saved,
            skipped=result.skipped,
            expected_answer=result.expected_answer,
            explanation=result.explanation,
            correct_options=_as_list(result.correct_options),
        )


def _as_list[T](values: tuple[T, ...] | None) -> list[T] | None:
    return list(values) if values is not None else None


class ClaimIn(BaseModel):
    handle: str = Field(min_length=1, max_length=20)


class ClaimOut(BaseModel):
    handle: str
    streak: int
    rank: int
    personal_best: bool


@router.post("", status_code=status.HTTP_201_CREATED)
def start_run(game: GameDep, body: RunIn | None = None) -> RunCreated:
    return RunCreated(run_id=game.start_run(body.language if body else DEFAULT_LANGUAGE))


@router.get("/{run_id}")
def get_run(run_id: uuid.UUID, game: GameDep) -> RunState:
    view = game.get_run(run_id)
    return RunState(
        run_id=view.run_id,
        over=view.over,
        streak=view.streak,
        lives=view.lives,
        combo=view.combo,
        open_question=QuestionOut.from_view(view.open_question) if view.open_question else None,
        last_expected_answer=view.last_expected_answer,
        last_explanation=view.last_explanation,
        last_format=view.last_format,
        last_options=_as_list(view.last_options),
        last_correct_options=_as_list(view.last_correct_options),
        last_selected_options=_as_list(view.last_selected_options),
        claimed_by=view.claimed_by,
    )


@router.post("/{run_id}/question")
def next_question(run_id: uuid.UUID, game: GameDep) -> QuestionOut:
    return QuestionOut.from_view(game.next_question(run_id))


@router.post("/{run_id}/question/start")
def start_question(run_id: uuid.UUID, game: GameDep) -> QuestionOut:
    return QuestionOut.from_view(game.start_question(run_id))


@router.post("/{run_id}/answer")
def answer(run_id: uuid.UUID, body: AnswerIn, game: GameDep) -> AnswerOut:
    return AnswerOut.from_result(game.answer(run_id, body.answer, body.selected))


@router.post("/{run_id}/skip")
def skip(run_id: uuid.UUID, game: GameDep) -> AnswerOut:
    return AnswerOut.from_result(game.skip(run_id))


@router.post("/{run_id}/timeout")
def time_out(run_id: uuid.UUID, game: GameDep) -> AnswerOut:
    return AnswerOut.from_result(game.time_out(run_id))


@router.post("/{run_id}/claim")
def claim(run_id: uuid.UUID, body: ClaimIn, leaderboard: LeaderboardDep) -> ClaimOut:
    result = leaderboard.claim(run_id, body.handle)
    return ClaimOut(
        handle=result.handle,
        streak=result.streak,
        rank=result.rank,
        personal_best=result.personal_best,
    )
