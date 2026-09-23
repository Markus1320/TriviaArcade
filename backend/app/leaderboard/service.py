"""Claiming finished runs under a handle, and reading the leaderboard."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
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
    rank: int


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
            return ClaimResult(handle=handle, streak=run.streak, rank=self._rank_of(run))

    def top(self, limit: int = LEADERBOARD_SIZE) -> list[LeaderboardEntry]:
        with self._session.begin():
            rows = self._session.execute(
                select(Run.id, Player.handle, Run.streak, Run.ended_at)
                .join(Player, Run.player_id == Player.id)
                .where(Run.status == RUN_OVER)
                .order_by(Run.streak.desc(), Run.ended_at.asc(), Run.id.asc())
                .limit(limit)
            ).all()
        finished = [
            FinishedRun(run_id=run_id, handle=handle, streak=streak, finished_at=ended_at)
            for run_id, handle, streak, ended_at in rows
        ]
        return rank_runs(finished, limit)

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

    def _rank_of(self, run: Run) -> int:
        """1 + the number of claimed runs that rank above this one."""
        assert run.ended_at is not None
        better = self._session.scalar(
            select(func.count())
            .select_from(Run)
            .where(
                Run.player_id.is_not(None),
                Run.id != run.id,
                or_(
                    Run.streak > run.streak,
                    and_(Run.streak == run.streak, Run.ended_at < run.ended_at),
                    and_(
                        Run.streak == run.streak,
                        Run.ended_at == run.ended_at,
                        Run.id < run.id,
                    ),
                ),
            )
        )
        return (better or 0) + 1
