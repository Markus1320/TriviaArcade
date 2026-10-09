"""Streak and game over rules (version one).

- The streak is the score: the number of correct answers in a row.
- One wrong answer ends the run. No lives, no skips.
- A technical judge failure is not a verdict and never reaches these rules.
- With a time limit, an answer must arrive within the limit after the question was shown,
  plus a short grace for network delay. A late answer ends the run like a wrong one.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

# Covers the delay between the browser's countdown reaching zero and the auto-submitted
# answer arriving at the server.
ANSWER_GRACE_SECONDS = 3.0


class RunAlreadyOverError(RuntimeError):
    pass


@dataclass(frozen=True)
class Progress:
    streak: int = 0
    over: bool = False


def apply_verdict(progress: Progress, correct: bool) -> Progress:
    if progress.over:
        raise RunAlreadyOverError("the run is already over")
    if correct:
        return Progress(streak=progress.streak + 1, over=False)
    return Progress(streak=progress.streak, over=True)


def seconds_left(shown_at: datetime, now: datetime, limit_seconds: float) -> float:
    """Seconds of the time limit still left, never below zero."""
    remaining = shown_at + timedelta(seconds=limit_seconds) - now
    return max(0.0, remaining.total_seconds())


def answer_in_time(
    shown_at: datetime,
    received_at: datetime,
    limit_seconds: float,
    grace_seconds: float = ANSWER_GRACE_SECONDS,
) -> bool:
    return received_at <= shown_at + timedelta(seconds=limit_seconds + grace_seconds)
