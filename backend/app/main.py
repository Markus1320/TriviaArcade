"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.db.engine import get_engine
from app.graph.driver import get_driver

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # Only close connections that were actually opened.
    if get_driver.cache_info().currsize:
        get_driver().close()
    if get_engine.cache_info().currsize:
        get_engine().dispose()


app = FastAPI(title="TriviaArcade", lifespan=lifespan)
app.include_router(health.router, prefix="/api")
