import pytest

from app.game.rules import Progress, RunAlreadyOverError, apply_verdict


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
