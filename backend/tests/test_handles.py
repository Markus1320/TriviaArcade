import pytest

from app.leaderboard.handles import InvalidHandleError, normalize_handle


@pytest.mark.parametrize(
    ("raw", "handle"),
    [
        ("ACE", "ACE"),
        ("ace", "ACE"),
        ("  Neo42 ", "NEO42"),
        ("ACE\n", "ACE"),  # surrounding whitespace is trimmed
        ("12345678", "12345678"),
        ("abcdefgh", "ABCDEFGH"),
    ],
)
def test_valid_handles_are_normalized(raw: str, handle: str) -> None:
    assert normalize_handle(raw) == handle


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "AB",  # too short
        "ABCDEFGHI",  # too long
        "A B C",  # spaces inside
        "ÄÖÜ",  # letters outside A-Z
        "ACE!",
        "ACE_1",
        "ab​c",  # zero width space
    ],
)
def test_invalid_handles_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidHandleError):
        normalize_handle(raw)
