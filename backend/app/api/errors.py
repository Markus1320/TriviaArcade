"""Maps domain errors to HTTP responses with a short message for the player."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.game.service import (
    GameError,
    InvalidAnswerError,
    JudgePausedError,
    NoOpenQuestionError,
    QuestionUnavailableError,
    RunNotFoundError,
    RunOverError,
)
from app.leaderboard.handles import InvalidHandleError
from app.leaderboard.service import RunAlreadyClaimedError, RunNotOverError

# Exception type -> (HTTP status, machine readable code, message shown to the player).
# Internal error details are logged, not sent to the browser.
_ERRORS: dict[type[Exception], tuple[int, str, str]] = {
    RunNotFoundError: (status.HTTP_404_NOT_FOUND, "run_not_found", "This run does not exist."),
    RunOverError: (status.HTTP_409_CONFLICT, "run_over", "This run is already over."),
    NoOpenQuestionError: (
        status.HTTP_409_CONFLICT,
        "no_open_question",
        "There is no question to answer.",
    ),
    InvalidAnswerError: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid_answer",
        "Please type an answer.",
    ),
    QuestionUnavailableError: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "question_unavailable",
        "Could not create a question right now. Please try again.",
    ),
    JudgePausedError: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "judge_unavailable",
        "The judge is not reachable right now. Your run is paused; send your answer again.",
    ),
    RunNotOverError: (
        status.HTTP_409_CONFLICT,
        "run_not_over",
        "Only finished runs can be added to the leaderboard.",
    ),
    RunAlreadyClaimedError: (
        status.HTTP_409_CONFLICT,
        "run_already_claimed",
        "This run is already on the leaderboard.",
    ),
}


def install_error_handlers(app: FastAPI) -> None:
    async def handle_game_error(_: Request, error: Exception) -> JSONResponse:
        status_code, code, message = _ERRORS.get(
            type(error), (status.HTTP_400_BAD_REQUEST, "game_error", "The request failed.")
        )
        return JSONResponse(status_code=status_code, content={"code": code, "detail": message})

    async def handle_invalid_handle(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"code": "invalid_handle", "detail": str(error)},
        )

    app.add_exception_handler(GameError, handle_game_error)
    app.add_exception_handler(InvalidHandleError, handle_invalid_handle)
