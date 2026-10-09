from datetime import UTC, datetime, timedelta

import pytest

from app.game.rules import (
    ANSWER_GRACE_SECONDS,
    Progress,
    RunAlreadyOverError,
    answer_in_time,
    apply_verdict,
    seconds_left,
)

SHOWN = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def test_correct_answer_increases_streak() -> None:
    assert apply_verdict(Progress(streak=3), correct=True) == Progress(streak=4, over=False)


def test_first_wrong_answer_ends_run_and_keeps_streak() -> None:
    assert apply_verdict(Progress(streak=3), correct=False) == Progress(streak=3, over=True)


def test_wrong_first_answer_scores_zero() -> None:
    assert apply_verdict(Progress(), correct=False) == Progress(streak=0, over=True)


def test_streak_counts_correct_answers_in_a_row() -> None:
    progress = Progress()
    for _ in range(5):
        progress = apply_verdict(progress, correct=True)
    assert progress == Progress(streak=5, over=False)


@pytest.mark.parametrize("correct", [True, False])
def test_no_verdict_after_game_over(correct: bool) -> None:
    with pytest.raises(RunAlreadyOverError):
        apply_verdict(Progress(streak=2, over=True), correct=correct)


def test_seconds_left_counts_down_and_stops_at_zero() -> None:
    assert seconds_left(SHOWN, SHOWN, 45) == 45
    assert seconds_left(SHOWN, SHOWN + timedelta(seconds=30), 45) == 15
    assert seconds_left(SHOWN, SHOWN + timedelta(seconds=60), 45) == 0


@pytest.mark.parametrize(
    ("after", "in_time"),
    [
        (0, True),
        (45, True),
        (45 + ANSWER_GRACE_SECONDS, True),
        (45 + ANSWER_GRACE_SECONDS + 0.1, False),
    ],
)
def test_answer_in_time_includes_grace(after: float, in_time: bool) -> None:
    assert answer_in_time(SHOWN, SHOWN + timedelta(seconds=after), 45) is in_time
