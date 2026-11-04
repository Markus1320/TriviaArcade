"""Typed answers checked by code. One table: the question, its correct answers, what the
player typed and whether it counts. Most cases come from real judge verdicts."""

import pytest

from game.matcher import match_answer

WHICH = "Which one?"
DANUBE = "Name three countries the Danube flows through."
DANUBE_COUNTRIES = ["Germany", "Austria", "Hungary", "Serbia", "Romania"]
NAME_TWO = "Nenne zwei Länder an der Donau."
CENTURY = "In which century did India gain independence?"


@pytest.mark.parametrize(
    ("question", "answers", "typed", "counts"),
    [
        # Case, accents, spacing, punctuation and articles do not matter.
        (WHICH, ["Reykjavík"], "reykjavik", True),
        (WHICH, ["Green Day"], "greenday", True),
        (WHICH, ["The Beatles"], "beatles!", True),
        (WHICH, ["Rhein"], "Der Rhein", True),
        (WHICH, ["Straße"], "strasse", True),
        (WHICH, ["Middle East"], "in the middle east", True),
        # Any listed form counts.
        (WHICH, ["Indonesia", "Indonesien"], "indonesien", True),
        # Small typos: swapped or missing letters, one wrong letter in a long word.
        (WHICH, ["Paris"], "Prais", True),
        (WHICH, ["Berlin"], "Berln", True),
        (WHICH, ["Pacific"], "Pcific", True),
        (WHICH, ["Neptune"], "Neptun", True),
        (WHICH, ["Mesopotamia"], "Mesopotamya", True),
        (WHICH, ["Bucharest"], "Bucharets", True),
        # A changed letter in a short word is another answer.
        (WHICH, ["Rhône", "Rhone"], "rhine", False),
        (WHICH, ["Iraq"], "Iran", False),
        (WHICH, ["złoty", "zloty"], "zlotk", False),
        (WHICH, ["AS Roma", "Roma"], "AC Roma", False),
        (WHICH, ["Austria"], "Australia", False),
        (WHICH, ["Slovakia"], "Slovenia", False),
        # Digits must match exactly.
        (WHICH, ["1789"], "1798", False),
        (WHICH, ["Africa"], "Europe", False),
        (WHICH, ["Paris"], "", False),
        # A century may be answered with its number.
        (CENTURY, ["20th century", "1900s"], "20", True),
        (CENTURY, ["20th century", "1900s"], "20. Jahrhundert", True),
        (CENTURY, ["20th century", "1900s"], "19", False),
        # "Name three" needs three different correct items.
        (DANUBE, DANUBE_COUNTRIES, "Germany, Austria and Hungary", True),
        (DANUBE, DANUBE_COUNTRIES, "romania; serbia & germny", True),
        (DANUBE, DANUBE_COUNTRIES, "Germany, Austria", False),
        (DANUBE, DANUBE_COUNTRIES, "Germany, Germany, Austria", False),
        (DANUBE, DANUBE_COUNTRIES, "Germany, Austria, France", False),
        (NAME_TWO, ["Deutschland", "Österreich"], "Österreich", False),
        (NAME_TWO, ["Deutschland", "Österreich"], "Österreich und Deutschland", True),
        # "Name a ..." needs only one.
        ("Name a country that borders Germany.", ["France", "Poland"], "Poland", True),
    ],
)
def test_match(question: str, answers: list[str], typed: str, counts: bool) -> None:
    assert match_answer(question, answers, typed) is counts
