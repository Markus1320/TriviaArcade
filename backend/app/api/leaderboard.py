"""Leaderboard and handle endpoints."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_leaderboard_service
from app.leaderboard.service import LeaderboardService

router = APIRouter(tags=["leaderboard"])

LeaderboardDep = Annotated[LeaderboardService, Depends(get_leaderboard_service)]


class LeaderboardRow(BaseModel):
    rank: int
    handle: str
    streak: int
    finished_at: datetime


@router.get("/leaderboard")
def leaderboard(service: LeaderboardDep) -> list[LeaderboardRow]:
    return [
        LeaderboardRow(
            rank=entry.rank, handle=entry.handle, streak=entry.streak, finished_at=entry.finished_at
        )
        for entry in service.top()
    ]


@router.get("/players")
def players(service: LeaderboardDep) -> list[str]:
    """Existing handles for the handle picker, most recently used first."""
    return service.handles()
