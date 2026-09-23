"""Health endpoint that checks both databases."""

import logging
from collections.abc import Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.db.engine import get_engine, ping_postgres
from app.graph.driver import get_driver, ping_neo4j

logger = logging.getLogger(__name__)

router = APIRouter()

Check = Callable[[], None]
ComponentStatus = Literal["ok", "error"]


class HealthResponse(BaseModel):
    status: ComponentStatus
    postgres: ComponentStatus
    neo4j: ComponentStatus


def get_postgres_check() -> Check:
    return lambda: ping_postgres(get_engine())


def get_neo4j_check() -> Check:
    return lambda: ping_neo4j(get_driver())


def _run(name: str, check: Check) -> ComponentStatus:
    try:
        check()
    except Exception:
        logger.warning("Health check failed for %s", name, exc_info=True)
        return "error"
    return "ok"


@router.get("/health", response_model=HealthResponse)
def health(
    response: Response,
    postgres_check: Annotated[Check, Depends(get_postgres_check)],
    neo4j_check: Annotated[Check, Depends(get_neo4j_check)],
) -> HealthResponse:
    postgres = _run("postgres", postgres_check)
    neo4j = _run("neo4j", neo4j_check)
    overall: ComponentStatus = "ok" if postgres == neo4j == "ok" else "error"
    if overall != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status=overall, postgres=postgres, neo4j=neo4j)
