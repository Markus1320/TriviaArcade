from datetime import UTC, datetime, timedelta

import pytest

from app.game.rules import (
    ANSWER_GRACE_SECONDS,
    LIFE_COMBO,
    MAX_LIVES,
    NoLifeLeftError,
    Progress,
    RunAlreadyOverError,
    answer_in_time,
    apply_skip,
    apply_verdict,
    choice_correct,
    order_correct,
    seconds_left,
)

SHOWN = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def test_correct_answer_increases_score_and_combo() -> None:
    assert apply_verdict(Progress(streak=3), correct=True) == Progress(streak=4, combo=1)


def test_first_wrong_answer_without_a_1up_ends_run_and_keeps_score() -> None:
    assert apply_verdict(Progress(streak=3, combo=2), correct=False) == Progress(
        streak=3, over=True
    )


def test_wrong_first_answer_scores_zero() -> None:
    assert apply_verdict(Progress(), correct=False) == Progress(streak=0, over=True)


def test_full_combo_earns_a_1up_and_starts_again() -> None:
    progress = Progress()
    for _ in range(LIFE_COMBO):
        progress = apply_verdict(progress, correct=True)
    assert progress == Progress(streak=LIFE_COMBO, lives=1, combo=0)


def test_1ups_stop_at_the_maximum() -> None:
    progress = Progress(streak=20, lives=MAX_LIVES, combo=LIFE_COMBO - 1)
    assert apply_verdict(progress, correct=True) == Progress(streak=21, lives=MAX_LIVES)


def test_wrong_answer_costs_a_1up_and_resets_the_combo() -> None:
    progress = Progress(streak=7, lives=2, combo=3)
    assert apply_verdict(progress, correct=False) == Progress(streak=7, lives=1, combo=0)


def test_skip_costs_a_1up_and_keeps_score_and_combo() -> None:
    assert apply_skip(Progress(streak=7, lives=2, combo=3)) == Progress(streak=7, lives=1, combo=3)


def test_skip_needs_a_1up() -> None:
    with pytest.raises(NoLifeLeftError):
        apply_skip(Progress(streak=7, combo=3))


@pytest.mark.parametrize("correct", [True, False])
def test_no_verdict_after_game_over(correct: bool) -> None:
    with pytest.raises(RunAlreadyOverError):
        apply_verdict(Progress(streak=2, over=True), correct=correct)
    with pytest.raises(RunAlreadyOverError):
        apply_skip(Progress(streak=2, over=True, lives=1))


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


@pytest.mark.parametrize(
    ("selected", "correct", "expected"),
    [
        ([1], [1], True),
        ([2, 0], [0, 2], True),
        ([0], [0, 2], False),
        ([0, 1, 2], [0, 2], False),
        ([], [1], False),
    ],
)
def test_choice_needs_exactly_the_correct_options(
    selected: list[int], correct: list[int], expected: bool
) -> None:
    assert choice_correct(selected, correct) is expected


@pytest.mark.parametrize(
    ("tapped", "correct"),
    [([2, 0, 1], True), ([0, 2, 1], False), ([2, 0], False), ([2, 0, 1, 3], False)],
)
def test_order_needs_every_option_in_the_correct_order(tapped: list[int], correct: bool) -> None:
    assert order_correct(tapped, [2, 0, 1]) is correct
