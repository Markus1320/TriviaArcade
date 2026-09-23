"""Leaderboard order: one entry per player, their best run.

A player's best run is their highest streak, the earlier finish winning a tie. Players are
then ordered the same way: highest streak first, ties broken by the earlier finish time.
The run ID only makes the order total, for two runs finishing in the same instant.
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


def best_per_player(runs: Iterable[FinishedRun]) -> list[FinishedRun]:
    best: dict[str, FinishedRun] = {}
    for run in runs:
        current = best.get(run.handle)
        if current is None or ranking_key(run) < ranking_key(current):
            best[run.handle] = run
    return list(best.values())


def rank_runs(
    runs: Iterable[FinishedRun], limit: int | None = LEADERBOARD_SIZE
) -> list[LeaderboardEntry]:
    """Rank each player's best run. limit=None ranks every player."""
    ordered = sorted(best_per_player(runs), key=ranking_key)
    if limit is not None:
        ordered = ordered[:limit]
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
