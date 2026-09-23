"""Leaderboard order: highest streak first, ties broken by the earlier finish time.

A player can appear several times. The run ID only makes the order total, for the
theoretical case of two runs finishing in the same instant.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

LEADERBOARD_SIZE = 10


@dataclass(frozen=True)
class FinishedRun:
    run_id: uuid.UUID
    handle: str
    streak: int
    finished_at: datetime


@dataclass(frozen=True)
class LeaderboardEntry:
    rank: int
    handle: str
    streak: int
    finished_at: datetime
    run_id: uuid.UUID


def ranking_key(run: FinishedRun) -> tuple[int, datetime, str]:
    return (-run.streak, run.finished_at, str(run.run_id))


def rank_runs(runs: Iterable[FinishedRun], limit: int = LEADERBOARD_SIZE) -> list[LeaderboardEntry]:
    ordered = sorted(runs, key=ranking_key)[:limit]
    return [
        LeaderboardEntry(
            rank=position,
            handle=run.handle,
            streak=run.streak,
            finished_at=run.finished_at,
            run_id=run.run_id,
        )
        for position, run in enumerate(ordered, start=1)
    ]
