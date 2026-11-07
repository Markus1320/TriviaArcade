"""The rules, as tables: each line is one case. Adding a case is adding a line."""

from datetime import UTC, datetime, timedelta

import pytest

from game.rules import (
    Progress,
    answer_in_time,
    apply_skip,
    apply_verdict,
    choice_correct,
    clean_answer,
    normalize_handle,
    order_correct,
    seconds_left,
)
from game.settings import Settings

# The defaults: a 1UP for 3 correct answers in a row, at most 3 in stock.
DEFAULT = Settings()
P = Progress


@pytest.mark.parametrize(
    ("before", "correct", "after"),
    [
        # A correct answer adds to the score and the combo.
        (P(score=3), True, P(score=4, combo=1)),
        # The third in a row earns a 1UP and starts the combo again.
        (P(score=2, combo=2), True, P(score=3, lives=1, combo=0)),
        # With a full stock the 1UP is lost.
        (P(score=20, lives=3, combo=2), True, P(score=21, lives=3, combo=0)),
        # A wrong answer costs a 1UP and resets the combo; the run goes on.
        (P(score=7, lives=2, combo=2), False, P(score=7, lives=1, combo=0)),
        # Without a 1UP a wrong answer ends the run and keeps the score.
        (P(score=3, combo=2), False, P(score=3, over=True)),
        (P(), False, P(over=True)),
    ],
)
def test_verdict(before: Progress, correct: bool, after: Progress) -> None:
    assert apply_verdict(before, correct, DEFAULT) == after


def test_other_life_settings() -> None:
    settings = Settings(life_combo=2, max_lives=1)
    assert apply_verdict(P(combo=1), True, settings) == P(score=1, lives=1, combo=0)


def test_skip_costs_a_1up_and_keeps_score_and_combo() -> None:
    assert apply_skip(P(score=7, lives=2, combo=2)) == P(score=7, lives=1, combo=2)


@pytest.mark.parametrize(
    ("selected", "correct", "right"),
    [
        ([1], [1], True),
        ([2, 0], [0, 2], True),  # the order of picking does not matter
        ([0], [0, 2], False),  # one missing
        ([0, 1, 2], [0, 2], False),  # one too many
        ([], [1], False),
    ],
)
def test_choice(selected: list[int], correct: list[int], right: bool) -> None:
    assert choice_correct(selected, correct) is right


@pytest.mark.parametrize(
    ("tapped", "right"),
    [
        ([2, 0, 1], True),
        ([0, 2, 1], False),  # wrong order
        ([2, 0], False),  # incomplete
    ],
)
def test_order(tapped: list[int], right: bool) -> None:
    assert order_correct(tapped, [2, 0, 1]) is right


SHOWN = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("after_seconds", "left", "in_time"),
    [
        (0, 30, True),
        (10, 20, True),
        (30, 0, True),
        (33, 0, True),  # 3 seconds grace for the network
        (33.1, 0, False),
    ],
)
def test_time_limit(after_seconds: float, left: float, in_time: bool) -> None:
    now = SHOWN + timedelta(seconds=after_seconds)
    assert seconds_left(SHOWN, now, 30) == left
    assert answer_in_time(SHOWN, now, 30) is in_time


@pytest.mark.parametrize(
    ("typed", "handle"),
    [
        ("abc", "ABC"),
        (" ace99 ", "ACE99"),
        ("ABCDEFGH", "ABCDEFGH"),
        ("AB", None),  # too short
        ("ABCDEFGHI", None),  # too long
        ("A-B-C", None),  # only letters and digits
        ("ÄÖÜ", None),
    ],
)
def test_handle(typed: str, handle: str | None) -> None:
    assert normalize_handle(typed) == handle


@pytest.mark.parametrize(
    ("typed", "cleaned"),
    [
        ("  Paris ", "Paris"),
        ("New\nYork  City", "New York City"),
        ("x" * 300, "x" * 200),
    ],
)
def test_clean_answer(typed: str, cleaned: str) -> None:
    assert clean_answer(typed) == cleaned
