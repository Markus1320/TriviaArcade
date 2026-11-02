"""The code matcher for typed answers. Cases come from real judge verdicts."""

import pytest

from app.game.matcher import (
    AnswerKey,
    edit_distance,
    items_required,
    match_answer,
    normalize_answer,
)


def key(question: str, *answers: str) -> AnswerKey:
    return AnswerKey.of(question, answers)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("  The Beatles!", "beatles"),
        ("Zürich", "zurich"),
        ("Straße", "strasse"),
        ("Der Rhein", "rhein"),
        ("In the Middle East", "middle east"),
        ("Złoty", "złoty"),  # ł has no decomposition and is kept
    ],
)
def test_normalize_answer(text: str, expected: str) -> None:
    assert normalize_answer(text) == expected


@pytest.mark.parametrize(
    ("answers", "player"),
    [
        (("Reykjavík",), "reykjavik"),  # accents
        (("Green Day",), "greenday"),  # spacing
        (("Indonesia", "Indonesien"), "indonesien"),  # listed translation
        (("Paris",), "Prais"),  # swapped neighbours in a short word
        (("Berlin",), "Berln"),  # missing letter in a short word
        (("Pacific",), "Pcific"),
        (("Neptune",), "Neptun"),
        (("Mesopotamia",), "Mesopotamya"),  # one wrong letter in a long word
        (("Bucharest",), "Bucharets"),
        (("Middle East",), "in the middle east"),
    ],
)
def test_accepted(answers: tuple[str, ...], player: str) -> None:
    assert match_answer(key("Which one?", *answers), player)


@pytest.mark.parametrize(
    ("answers", "player"),
    [
        (("Rhône", "Rhone"), "rhine"),  # a changed letter in a short word is another river
        (("złoty", "zloty"), "zlotk"),
        (("AS Roma", "Roma"), "AC Roma"),
        (("Iraq",), "Iran"),
        (("Austria",), "Australia"),
        (("Slovakia",), "Slovenia"),
        (("1789",), "1798"),  # digits must match
        (("Africa",), "Europe"),
        (("Paris",), ""),
    ],
)
def test_rejected(answers: tuple[str, ...], player: str) -> None:
    assert not match_answer(key("Which one?", *answers), player)


def test_century_may_be_answered_with_the_number() -> None:
    century = key("In which century did India gain independence?", "20th century", "1900s")
    assert match_answer(century, "20")
    assert match_answer(century, "20. Jahrhundert")
    assert not match_answer(century, "19")


def test_name_several_needs_that_many_distinct_items() -> None:
    question = key(
        "Name three countries the Danube flows through.",
        "Germany",
        "Austria",
        "Hungary",
        "Serbia",
        "Romania",
    )
    assert match_answer(question, "Germany, Austria and Hungary")
    assert match_answer(question, "romania; serbia & germny")
    assert not match_answer(question, "Germany, Austria")
    assert not match_answer(question, "Germany, Germany, Austria")
    assert not match_answer(question, "Germany, Austria, France")


@pytest.mark.parametrize(
    ("question", "count"),
    [
        ("Name three countries the Danube flows through.", 3),
        ("Nenne zwei Länder, die an Frankreich grenzen.", 2),
        ("Name a country that borders Germany.", 1),
        ("Which country has three official languages?", 1),
    ],
)
def test_items_required(question: str, count: int) -> None:
    assert items_required(question) == count


def test_edit_distance_counts_swaps_once_and_stops_at_the_limit() -> None:
    assert edit_distance("paris", "prais", 2) == 1
    assert edit_distance("kitten", "sitting", 5) == 3
    assert edit_distance("abcdef", "uvwxyz", 2) == 3
