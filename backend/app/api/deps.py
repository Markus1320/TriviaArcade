"""FastAPI dependencies. Tests override these to use fakes instead of Neo4j and the LLM."""

import random
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.engine import get_session_factory
from app.game.service import AnswerChecker, GameService, QuestionSource, SeedSource
from app.graph.driver import get_driver
from app.graph.repository import Neo4jGraphRepository
from app.graph.walk import RandomWalker
from app.leaderboard.service import LeaderboardService
from app.llm.call_log import SqlCallLogger
from app.llm.factory import LLMComponents, LLMNotConfiguredError, build_llm_components


def get_session() -> Iterator[Session]:
    with get_session_factory()() as session:
        yield session


@lru_cache
def _llm_components() -> LLMComponents:
    return build_llm_components(get_settings(), SqlCallLogger(get_session_factory()))


def _llm() -> LLMComponents:
    try:
        return _llm_components()
    except LLMNotConfiguredError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"The LLM is not configured: {error}"
        ) from error


@lru_cache
def get_seed_source() -> SeedSource:
    return RandomWalker(Neo4jGraphRepository(get_driver()), random.Random())


def get_question_source() -> QuestionSource:
    return _llm().generator


def get_answer_checker() -> AnswerChecker:
    return _llm().judge


def get_game_service(
    session: Annotated[Session, Depends(get_session)],
    seeds: Annotated[SeedSource, Depends(get_seed_source)],
    generator: Annotated[QuestionSource, Depends(get_question_source)],
    judge: Annotated[AnswerChecker, Depends(get_answer_checker)],
) -> GameService:
    return GameService(session, seeds, generator, judge)


def get_leaderboard_service(
    session: Annotated[Session, Depends(get_session)],
) -> LeaderboardService:
    return LeaderboardService(session)
