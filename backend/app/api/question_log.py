"""The question log: recent questions of finished runs, anonymous."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.deps import get_question_log_service
from app.questionlog.service import LOG_SIZE, QuestionLogService

router = APIRouter(tags=["question log"])

QuestionLogDep = Annotated[QuestionLogService, Depends(get_question_log_service)]


class LoggedQuestionOut(BaseModel):
    id: int
    run_ended_at: datetime
    language: str
    number: int
    correct: bool
    # Skipped with a 1UP: neither right nor wrong.
    skipped: bool
    format: str
    question: str
    # Choice questions: options in the shown order, correct_options as positions in it.
    options: list[str]
    correct_options: list[int]
    expected_answer: str
    accepted_answers: list[str]
    explanation: str | None
    # The generator's note fields: topic, candidates, choice, review.
    notes: dict[str, Any]
    model: str
    # The user message sent to the generator.
    prompt: str


class QuestionLogPage(BaseModel):
    questions: list[LoggedQuestionOut]
    has_more: bool


@router.get("/question-log")
def question_log(
    service: QuestionLogDep, offset: Annotated[int, Query(ge=0, le=LOG_SIZE)] = 0
) -> QuestionLogPage:
    page = service.page(offset)
    return QuestionLogPage(
        questions=[LoggedQuestionOut(**asdict(question)) for question in page.questions],
        has_more=page.has_more,
    )
