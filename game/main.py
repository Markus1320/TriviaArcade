"""The web app: every HTTP route of the game under /api, and the built frontend.

Start it with:

    uv run uvicorn game.main:create_app --factory

--factory tells uvicorn to call create_app() to get the app, so the settings are read
when the server starts (and tests can pass their own).

FastAPI calls a route function for each request. Its parameters say what the function
needs: a path part (run_id), the JSON body (checked by a Pydantic model such as AnswerIn)
or a dependency (Db: an open database connection, closed again after the request).
"""

import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from game import db, runs, scores
from game.rules import MAX_ANSWER_LENGTH
from game.runs import GameError
from game.settings import Settings, load_settings

logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/api")


def open_db(request: Request) -> Iterator[sqlite3.Connection]:
    connection = db.connect(request.app.state.settings.database)
    try:
        yield connection
    finally:
        connection.close()


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


Db = Annotated[sqlite3.Connection, Depends(open_db)]
Config = Annotated[Settings, Depends(get_settings)]


# Request bodies. FastAPI answers 422 when a body does not fit.


class RunIn(BaseModel):
    language: Literal["en", "de"] = "en"


class AnswerIn(BaseModel):
    """A typed answer for free questions, or the picked option positions for the others."""

    answer: str | None = Field(default=None, min_length=1, max_length=MAX_ANSWER_LENGTH)
    selected: list[int] | None = Field(default=None, min_length=1, max_length=10)

    @model_validator(mode="after")
    def exactly_one(self) -> "AnswerIn":
        if (self.answer is None) == (self.selected is None):
            raise ValueError("send either answer or selected")
        return self


class ClaimIn(BaseModel):
    handle: str = Field(min_length=1, max_length=20)


# Routes.


@router.get("/health")
def health(connection: Db) -> dict:
    connection.execute("SELECT 1")
    return {"status": "ok"}


@router.post("/runs", status_code=201)
def start_run(connection: Db, settings: Config, body: RunIn | None = None) -> dict:
    language = body.language if body else "en"
    return {"run_id": runs.start_run(connection, settings, language)}


@router.get("/runs/{run_id}")
def get_run(run_id: str, connection: Db, settings: Config) -> dict:
    return runs.get_run(connection, settings, run_id)


@router.post("/runs/{run_id}/question")
def next_question(run_id: str, connection: Db, settings: Config) -> dict:
    return runs.next_question(connection, settings, run_id)


@router.post("/runs/{run_id}/question/start")
def start_question(run_id: str, connection: Db, settings: Config) -> dict:
    return runs.start_question(connection, settings, run_id)


@router.post("/runs/{run_id}/answer")
def answer(run_id: str, body: AnswerIn, connection: Db, settings: Config) -> dict:
    return runs.answer(connection, settings, run_id, body.answer, body.selected)


@router.post("/runs/{run_id}/skip")
def skip(run_id: str, connection: Db, settings: Config) -> dict:
    return runs.skip(connection, settings, run_id)


@router.post("/runs/{run_id}/timeout")
def time_out(run_id: str, connection: Db, settings: Config) -> dict:
    return runs.time_out(connection, settings, run_id)


@router.post("/runs/{run_id}/claim")
def claim(run_id: str, body: ClaimIn, connection: Db) -> dict:
    return scores.claim(connection, run_id, body.handle)


@router.get("/leaderboard")
def leaderboard(connection: Db) -> list[dict]:
    return scores.leaderboard(connection)


@router.get("/players")
def players(connection: Db) -> list[str]:
    return scores.handles(connection)


@router.get("/question-log")
def question_log(
    connection: Db,
    settings: Config,
    offset: Annotated[int, Query(ge=0, le=scores.LOG_SIZE)] = 0,
) -> dict:
    return scores.question_log(connection, settings, offset)


def game_error(_: Request, error: Exception) -> JSONResponse:
    """A GameError becomes a response like {"code": "run_over", "detail": "..."}."""
    assert isinstance(error, GameError)
    return JSONResponse(
        status_code=error.status, content={"code": error.code, "detail": error.detail}
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db.create_tables(settings.database)
    app = FastAPI(title="TriviaArcade")
    app.state.settings = settings
    app.include_router(router)
    app.add_exception_handler(GameError, game_error)
    # Everything that is not /api: the files of the built frontend. html=True serves
    # index.html for "/". Mounted last, so the /api routes come first.
    if Path(settings.frontend_dir).is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True))
    return app
