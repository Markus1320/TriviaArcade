"""Judges a typed answer by code, against every known form of the correct answer.

Replaces the LLM judge for pool questions, which carry long answer lists: the generator's
expected and accepted answers, the blind solver's answers and the graph aliases of the
answer entity.

- Case, accents, punctuation, spacing and a leading article do not matter.
- Small typos are accepted; how many depends on the length of the word (see
  allowed_typos). Digits must match exactly, so years and numbers are never "close".
- "Name three ..." questions need that many distinct correct items, separated by commas,
  "and" or "und".
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# Dropped from the start of an answer: articles, and "in" for answers to "where" questions
# ("in the Middle East").
LEADING_WORDS = (
    "in the ", "in der ", "in den ", "im ", "in ",
    "the ", "a ", "an ", "der ", "die ", "das ", "le ", "la ", "les ",
)  # fmt: skip
# "19th century" may also be answered "19".
_CENTURY = re.compile(r"^(\d+)(?:st|nd|rd|th)? (?:century|jahrhundert)$")
_ITEM_SEPARATORS = re.compile(r"\s*(?:,|;|/|&|\+|\band\b|\bund\b)\s*")
_NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5,
    "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
}  # fmt: skip
_NAME_SEVERAL = re.compile(
    r"\b(?:name|list|give|nenne|nennen sie|zähle|zaehle)\s+(?:any\s+|mindestens\s+)?"
    r"(two|three|four|five|zwei|drei|vier|fünf|fuenf|[2-5])\b",
    re.IGNORECASE,
)


def normalize_answer(text: str) -> str:
    """Case, accents, punctuation and leading articles do not matter."""
    decomposed = unicodedata.normalize("NFKD", text.casefold().replace("ß", "ss"))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    words = " ".join(re.findall(r"\w+", plain))
    for prefix in LEADING_WORDS:
        if words.startswith(prefix) and len(words) > len(prefix):
            words = words[len(prefix) :]
    return words


def allowed_typos(length: int) -> int:
    """Edits accepted for a word of this many letters. Short names differ by one letter
    (Iran and Iraq, Rhine and Rhone), so up to six letters a changed letter is never a
    typo; only a missing, an extra or two swapped letters are (see forms_match). Slovakia
    and Slovenia are two edits apart."""
    if length <= 6:
        return 0
    if length <= 8:
        return 1
    return 2


def _swapped_neighbours(a: str, b: str) -> bool:
    """The same letters, with exactly two adjacent ones swapped ("Prais" for "Paris")."""
    if len(a) != len(b) or a == b:
        return False
    diff = [i for i, (x, y) in enumerate(zip(a, b, strict=True)) if x != y]
    return (
        len(diff) == 2
        and diff[1] == diff[0] + 1
        and a[diff[0]] == b[diff[1]]
        and (a[diff[1]] == b[diff[0]])
    )


def edit_distance(a: str, b: str, limit: int) -> int:
    """Damerau-Levenshtein distance (adjacent swaps count once); limit + 1 when larger."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2: list[int] = []
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            cost = 0 if char_a == char_b else 1
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if i > 1 and j > 1 and char_a == b[j - 2] and a[i - 2] == char_b:
                value = min(value, previous2[j - 2] + 1)
            current.append(value)
        if min(current) > limit:
            return limit + 1
        previous2, previous = previous, current
    return previous[-1]


def _digits(text: str) -> list[str]:
    return re.findall(r"\d+", text)


def forms_match(player: str, correct: str) -> bool:
    """Both already normalized."""
    if not player or not correct:
        return False
    if player == correct or player.replace(" ", "") == correct.replace(" ", ""):
        return True
    if _digits(player) != _digits(correct):
        return False
    a, b = player.replace(" ", ""), correct.replace(" ", "")
    limit = allowed_typos(min(len(a), len(b)))
    if limit == 0:
        if min(len(a), len(b)) < 4:
            return False
        if abs(len(a) - len(b)) == 1 and min(len(a), len(b)) >= 5:
            return edit_distance(a, b, 1) <= 1
        return _swapped_neighbours(a, b)
    return edit_distance(a, b, limit) <= limit


def items_required(question: str) -> int:
    """How many items a "Name three ..." question asks for; 1 for every other question."""
    found = _NAME_SEVERAL.search(question)
    if found is None:
        return 1
    word = found.group(1).casefold()
    return int(word) if word.isdigit() else _NUMBER_WORDS[word]


@dataclass(frozen=True)
class AnswerKey:
    question: str
    answers: tuple[str, ...]

    @classmethod
    def of(cls, question: str, *answer_lists: Iterable[str]) -> "AnswerKey":
        forms: list[str] = []
        for answers in answer_lists:
            for answer in answers:
                for variant in _variants(normalize_answer(answer)):
                    if variant not in forms:
                        forms.append(variant)
        return cls(question=question, answers=tuple(forms))


def _variants(form: str) -> list[str]:
    """A normalized form, and the bare number of a century ("19th century", "19")."""
    if not form:
        return []
    century = _CENTURY.match(form)
    return [form, century.group(1)] if century else [form]


def _matching(player: str, forms: Sequence[str]) -> str | None:
    """The correct form the normalized answer matches, if any."""
    for variant in _variants(player):
        for form in forms:
            if forms_match(variant, form):
                return form
    return None


def match_answer(key: AnswerKey, player_answer: str) -> bool:
    needed = items_required(key.question)
    whole = normalize_answer(player_answer)
    if needed == 1:
        return _matching(whole, key.answers) is not None
    items = [normalize_answer(part) for part in _ITEM_SEPARATORS.split(player_answer)]
    matched = set()
    for item in items:
        if not item:
            continue
        form = _matching(item, key.answers)
        if form is None:
            return False
        matched.add(form)
    # Distinct answers, not two spellings of the same one: "USA, United States" names one
    # country. Forms of one answer are not linked, so this only catches identical forms.
    return len(matched) >= needed
