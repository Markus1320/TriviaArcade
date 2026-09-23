"""Claiming finished runs under a handle, and reading the leaderboard."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import RUN_OVER, Player, Run
from app.game.service import GameError, RunNotFoundError, utc_now
from app.leaderboard.handles import normalize_handle
from app.leaderboard.ranking import LEADERBOARD_SIZE, FinishedRun, LeaderboardEntry, rank_runs


class RunNotOverError(GameError):
    pass


class RunAlreadyClaimedError(GameError):
    pass


@dataclass(frozen=True)
class ClaimResult:
    handle: str
    streak: int
    # The player's leaderboard rank, based on their best run (may be below the top 10).
    rank: int
    # Whether this run is now the player's best run, i.e. their leaderboard entry.
    personal_best: bool


class LeaderboardService:
    def __init__(self, session: Session, clock: Callable[[], datetime] = utc_now) -> None:
        self._session = session
        self._clock = clock

    def claim(self, run_id: uuid.UUID, raw_handle: str) -> ClaimResult:
        """Attach a finished run to a handle; creates the player on first use.

        Raises InvalidHandleError, RunNotFoundError, RunNotOverError or
        RunAlreadyClaimedError. A run can be claimed exactly once.
        """
        handle = normalize_handle(raw_handle)
        with self._session.begin():
            run = self._session.scalars(
                select(Run).where(Run.id == run_id).with_for_update()
            ).one_or_none()
            if run is None:
                raise RunNotFoundError(f"run {run_id} not found")
            if run.status != RUN_OVER:
                raise RunNotOverError("only finished runs can be added to the leaderboard")
            if run.player_id is not None:
                raise RunAlreadyClaimedError("this run is already on the leaderboard")

            player = self._session.scalars(
                select(Player).where(Player.handle == handle)
            ).one_or_none()
            if player is None:
                player = Player(handle=handle)
                self._session.add(player)
            run.player = player
            run.claimed_at = self._clock()
            self._session.flush()

            ranked = rank_runs(self._best_runs(_best_runs_query()), limit=None)
            entry = next(e for e in ranked if e.handle == handle)
            return ClaimResult(
                handle=handle,
                streak=run.streak,
                rank=entry.rank,
                personal_best=entry.run_id == run.id,
            )

    def top(self, limit: int = LEADERBOARD_SIZE) -> list[LeaderboardEntry]:
        """The best run of each player, the top `limit` players."""
        with self._session.begin():
            query = _best_runs_query()
            columns = query.selected_columns
            query = query.order_by(
                columns.streak.desc(), columns.ended_at.asc(), columns.id.asc()
            ).limit(limit)
            return rank_runs(self._best_runs(query), limit)

    def _best_runs(self, query: Select[tuple[uuid.UUID, str, int, datetime]]) -> list[FinishedRun]:
        return [
            FinishedRun(run_id=run_id, handle=handle, streak=streak, finished_at=ended_at)
            for run_id, handle, streak, ended_at in self._session.execute(query).all()
        ]

    def handles(self) -> list[str]:
        """Existing handles, most recently used first."""
        with self._session.begin():
            last_used = func.max(func.coalesce(Run.claimed_at, Player.created_at))
            rows = self._session.execute(
                select(Player.handle)
                .outerjoin(Run, Run.player_id == Player.id)
                .group_by(Player.id, Player.handle)
                .order_by(last_used.desc(), Player.handle)
            ).scalars()
            return list(rows)


def _best_runs_query() -> Select[tuple[uuid.UUID, str, int, datetime]]:
    """Each player's best claimed run (highest streak, earlier finish), one row per player."""
    position = (
        func.row_number()
        .over(
            partition_by=Run.player_id,
            order_by=(Run.streak.desc(), Run.ended_at.asc(), Run.id.asc()),
        )
        .label("position")
    )
    ranked = (
        select(Run.id, Run.player_id, Run.streak, Run.ended_at, position)
        .where(Run.player_id.is_not(None), Run.status == RUN_OVER)
        .subquery()
    )
    return (
        select(ranked.c.id, Player.handle, ranked.c.streak, ranked.c.ended_at)
        .join(Player, Player.id == ranked.c.player_id)
        .where(ranked.c.position == 1)
    )
