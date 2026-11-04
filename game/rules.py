"""The rules of the game, as plain functions without a database.

- The score is the number of correct answers in the run.
- A run starts with settings.start_lives 1UPs. Every settings.life_combo correct answers
  in a row earn one more, up to settings.max_lives in stock.
- A wrong answer costs a 1UP if there is one, resets the combo and the run goes on;
  without a 1UP it ends the run.
- A 1UP can also be spent to skip a question. A skip adds nothing to the score and keeps
  the combo where it was.
- Choice questions: exactly the correct options must be picked. Order questions: every
  option, in exactly the correct order.
- An answer must arrive within the time limit after the question was shown, plus a short
  grace for network delay. A late answer counts as wrong.
- Handles have 3 to 8 characters, letters A-Z and digits.
"""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from game.settings import Settings

# Covers the delay between the browser's countdown reaching zero and the answer it then
# sends arriving at the server.
ANSWER_GRACE_SECONDS = 3.0

# Longer typed answers are cut to this length.
MAX_ANSWER_LENGTH = 200

HANDLE_PATTERN = re.compile(r"^[A-Z0-9]{3,8}$")


@dataclass(frozen=True)
class Progress:
    score: int = 0
    lives: int = 0
    # Correct answers in a row since the last 1UP or wrong answer.
    combo: int = 0
    over: bool = False


def apply_verdict(progress: Progress, correct: bool, settings: Settings) -> Progress:
    """The run after a correct or wrong answer."""
    if correct:
        combo = progress.combo + 1
        lives = progress.lives
        if combo >= settings.life_combo:
            # A full combo starts again; with a full stock the 1UP is lost.
            combo = 0
            lives = min(lives + 1, settings.max_lives)
        return replace(progress, score=progress.score + 1, lives=lives, combo=combo)
    if progress.lives > 0:
        return replace(progress, lives=progress.lives - 1, combo=0)
    return replace(progress, combo=0, over=True)


def apply_skip(progress: Progress) -> Progress:
    """The run after skipping a question. The caller checks that there is a 1UP."""
    return replace(progress, lives=progress.lives - 1)


def choice_correct(selected: Collection[int], correct: Collection[int]) -> bool:
    """All correct options picked and no wrong one. Holds for single and multiple choice."""
    return set(selected) == set(correct)


def order_correct(tapped: Sequence[int], correct: Sequence[int]) -> bool:
    """Every option tapped, in exactly the correct order. No partial credit."""
    return list(tapped) == list(correct)


def seconds_left(shown: datetime, now: datetime, limit_seconds: float) -> float:
    """Seconds of the time limit still left, never below zero."""
    remaining = shown + timedelta(seconds=limit_seconds) - now
    return max(0.0, remaining.total_seconds())


def answer_in_time(shown: datetime, received: datetime, limit_seconds: float) -> bool:
    return received <= shown + timedelta(seconds=limit_seconds + ANSWER_GRACE_SECONDS)


def clean_answer(text: str) -> str:
    """Spaces and line breaks collapsed to single spaces, cut to MAX_ANSWER_LENGTH."""
    return " ".join(text.split())[:MAX_ANSWER_LENGTH]


def normalize_handle(text: str) -> str | None:
    """The handle in upper case, or None when it is not a valid handle."""
    handle = text.strip().upper()
    return handle if HANDLE_PATTERN.fullmatch(handle) else None
