"""Run endpoints: start, question, answer, state and claim."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.api.deps import get_game_service, get_leaderboard_service
from app.game.service import GameService, QuestionView
from app.leaderboard.service import LeaderboardService
from app.llm.judge import MAX_ANSWER_LENGTH

router = APIRouter(prefix="/runs", tags=["runs"])

GameDep = Annotated[GameService, Depends(get_game_service)]
LeaderboardDep = Annotated[LeaderboardService, Depends(get_leaderboard_service)]


class RunCreated(BaseModel):
    run_id: uuid.UUID


class QuestionOut(BaseModel):
    question_id: int
    number: int
    text: str
    streak: int

    @classmethod
    def from_view(cls, view: QuestionView) -> "QuestionOut":
        return cls(
            question_id=view.question_id, number=view.number, text=view.text, streak=view.streak
        )


class RunState(BaseModel):
    run_id: uuid.UUID
    over: bool
    streak: int
    open_question: QuestionOut | None
    last_expected_answer: str | None
    claimed_by: str | None


class AnswerIn(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_LENGTH)


class AnswerOut(BaseModel):
    correct: bool
    streak: int
    game_over: bool
    expected_answer: str | None


class ClaimIn(BaseModel):
    handle: str = Field(min_length=1, max_length=20)


class ClaimOut(BaseModel):
    handle: str
    streak: int
    rank: int
    personal_best: bool


@router.post("", status_code=status.HTTP_201_CREATED)
def start_run(game: GameDep) -> RunCreated:
    return RunCreated(run_id=game.start_run())


@router.get("/{run_id}")
def get_run(run_id: uuid.UUID, game: GameDep) -> RunState:
    view = game.get_run(run_id)
    return RunState(
        run_id=view.run_id,
        over=view.over,
        streak=view.streak,
        open_question=QuestionOut.from_view(view.open_question) if view.open_question else None,
        last_expected_answer=view.last_expected_answer,
        claimed_by=view.claimed_by,
    )


@router.post("/{run_id}/question")
def next_question(run_id: uuid.UUID, game: GameDep) -> QuestionOut:
    return QuestionOut.from_view(game.next_question(run_id))


@router.post("/{run_id}/answer")
def answer(run_id: uuid.UUID, body: AnswerIn, game: GameDep) -> AnswerOut:
    result = game.answer(run_id, body.answer)
    return AnswerOut(
        correct=result.correct,
        streak=result.streak,
        game_over=result.game_over,
        expected_answer=result.expected_answer,
    )


@router.post("/{run_id}/claim")
def claim(run_id: uuid.UUID, body: ClaimIn, leaderboard: LeaderboardDep) -> ClaimOut:
    result = leaderboard.claim(run_id, body.handle)
    return ClaimOut(
        handle=result.handle,
        streak=result.streak,
        rank=result.rank,
        personal_best=result.personal_best,
    )
