"""Score, 1UP and game over rules.

- The score (stored as the run's streak) is the number of correct answers in the run.
- A run starts with LifeRules.start_lives 1UPs. Every LifeRules.combo correct answers in a
  row earn one more, up to LifeRules.max_lives in stock (all set in the environment).
- A wrong answer costs a 1UP if there is one, resets the combo and the run goes on;
  without a 1UP it ends the run.
- A 1UP can also be spent to skip a question. A skip adds nothing to the score and keeps
  the combo where it was.
- A technical judge failure is not a verdict and never reaches these rules.
- Choice questions are checked by code: exactly the correct options must be selected.
- With a time limit, an answer must arrive within the limit after the question was shown,
  plus a short grace for network delay. A late answer ends the run like a wrong one.
"""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

# Covers the delay between the browser's countdown reaching zero and the auto-submitted
# answer arriving at the server.
ANSWER_GRACE_SECONDS = 3.0


@dataclass(frozen=True)
class LifeRules:
    # Correct answers in a row that earn a 1UP.
    combo: int = 3
    # The most 1UPs a player can hold.
    max_lives: int = 3
    # 1UPs a new run starts with.
    start_lives: int = 1

    def __post_init__(self) -> None:
        if self.combo < 1:
            raise ValueError("combo must be at least 1")
        if not 0 <= self.start_lives <= self.max_lives:
            raise ValueError("start_lives must be between 0 and max_lives")


class RunAlreadyOverError(RuntimeError):
    pass


class NoLifeLeftError(RuntimeError):
    pass


@dataclass(frozen=True)
class Progress:
    streak: int = 0
    over: bool = False
    lives: int = 0
    # Correct answers in a row since the last 1UP or wrong answer.
    combo: int = 0


def apply_verdict(progress: Progress, correct: bool, rules: LifeRules | None = None) -> Progress:
    rules = rules or LifeRules()
    if progress.over:
        raise RunAlreadyOverError("the run is already over")
    if correct:
        combo = progress.combo + 1
        lives = progress.lives
        if combo >= rules.combo:
            # A full combo starts again; with a full stock the 1UP is lost.
            combo = 0
            lives = min(lives + 1, rules.max_lives)
        return replace(progress, streak=progress.streak + 1, lives=lives, combo=combo)
    if progress.lives > 0:
        return replace(progress, lives=progress.lives - 1, combo=0)
    return replace(progress, over=True, combo=0)


def apply_skip(progress: Progress) -> Progress:
    if progress.over:
        raise RunAlreadyOverError("the run is already over")
    if progress.lives <= 0:
        raise NoLifeLeftError("no 1UP left to skip with")
    return replace(progress, lives=progress.lives - 1)


def choice_correct(selected: Collection[int], correct: Collection[int]) -> bool:
    """All correct options selected and no wrong one. Holds for single and multiple choice."""
    return set(selected) == set(correct)


def order_correct(tapped: Sequence[int], correct: Sequence[int]) -> bool:
    """Every option tapped, in exactly the correct order. No partial credit."""
    return list(tapped) == list(correct)


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
