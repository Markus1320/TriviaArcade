"""Streak and game over rules (version one).

- The streak is the score: the number of correct answers in a row.
- One wrong answer ends the run. No lives, no skips.
- A technical judge failure is not a verdict and never reaches these rules.
"""

from dataclasses import dataclass


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
