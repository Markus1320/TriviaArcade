"""The question pool: reading <pool_dir>/<language>.jsonl and picking questions from it.

Each line of the file is one question as JSON, written by the offline part (poolgen).
The game only reads the file. It is read again when it changes, so new questions are
used without a restart.
"""

import json
import logging
import random
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from game.matcher import normalize_answer

logger = logging.getLogger(__name__)

# When every question has been asked, one of this many asked longest ago is picked.
LEAST_RECENT_CHOICES = 50

# Option pairs that keep their usual order instead of being shuffled.
FIXED_ORDERS = (
    ("true", "false"),
    ("yes", "no"),
    ("wahr", "falsch"),
    ("richtig", "falsch"),
    ("ja", "nein"),
)


@dataclass(frozen=True)
class PoolQuestion:
    id: str
    language: str
    # The entity type of the walk's start; questions are picked evenly over the types.
    start_type: str
    # "free" (typed), "single", "multiple" or "order".
    format: str
    text: str
    # Empty for free questions.
    options: list[str]
    # The correct options; for order questions every option, in the correct order.
    correct_options: list[str]
    expected_answer: str
    # Free questions: every other form a typed answer may take (the writer's accepted
    # answers and the blind solver's answers). Empty for choice questions.
    accepted_answers: list[str]
    explanation: str
    # The writer's notes before the question (topic, candidates, choice, review).
    notes: dict[str, object]
    model: str
    # The writer's request for this question, shown in the question log.
    prompt: str


def from_record(record: dict) -> PoolQuestion:
    """One line of the pool file, as written by poolgen."""
    question = record["question"]
    accepted = []
    if question["format"] == "free":
        seen = {normalize_answer(question["expected_answer"])}
        for answer in question.get("accepted_answers", []) + record.get("solver_answers", []):
            form = normalize_answer(answer)
            if form and form not in seen:
                seen.add(form)
                accepted.append(answer)
    return PoolQuestion(
        id=record["id"],
        language=record["language"],
        start_type=record["start_type"],
        format=question["format"],
        text=question["question"],
        options=question.get("options", []),
        correct_options=question.get("correct_options", []),
        expected_answer=question["expected_answer"],
        accepted_answers=accepted,
        explanation=question.get("explanation", ""),
        notes={key: question.get(key) for key in ("topic", "candidates", "choice", "review")},
        model=record.get("generator_model", ""),
        prompt=record.get("prompt", ""),
    )


# File path -> (modification time and size when read, the questions in it).
_cache: dict[Path, tuple[tuple[float, int], list[PoolQuestion]]] = {}


def load(pool_dir: str, language: str) -> list[PoolQuestion]:
    """All questions in one language; an empty list when there is no pool file."""
    path = Path(pool_dir) / f"{language}.jsonl"
    try:
        stat = path.stat()
    except FileNotFoundError:
        return []
    version = (stat.st_mtime, stat.st_size)
    cached = _cache.get(path)
    if cached is not None and cached[0] == version:
        return cached[1]

    questions = []
    seen = set()
    with path.open(encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                question = from_record(json.loads(line))
            except (ValueError, KeyError, TypeError):
                # Also a half written last line while poolgen is still appending.
                logger.warning("Skipping unreadable line %d of %s", number, path)
                continue
            if question.id not in seen:
                seen.add(question.id)
                questions.append(question)
    _cache[path] = (version, questions)
    return questions


def find(pool_dir: str, language: str, pool_id: str) -> PoolQuestion | None:
    for question in load(pool_dir, language):
        if question.id == pool_id:
            return question
    return None


def pick(
    questions: list[PoolQuestion],
    last_asked: Mapping[str, int],
    in_this_run: Collection[str],
    rng: random.Random,
) -> PoolQuestion | None:
    """The next question for a run, or None when the run has had every question.

    last_asked maps every question any run has had to a number that grows with time.
    A question nobody has had comes first: an entity type is picked first, evenly, then
    a question of that type, so every type keeps its share. When all have been asked,
    one of those asked longest ago is picked. Never one this run already had.
    """
    candidates = [q for q in questions if q.id not in in_this_run]
    if not candidates:
        return None
    unasked: dict[str, list[PoolQuestion]] = {}
    for question in candidates:
        if question.id not in last_asked:
            unasked.setdefault(question.start_type, []).append(question)
    if unasked:
        start_type = rng.choice(sorted(unasked))
        return rng.choice(unasked[start_type])
    candidates.sort(key=lambda question: last_asked[question.id])
    return rng.choice(candidates[:LEAST_RECENT_CHOICES])


def shuffled_options(question: PoolQuestion, rng: random.Random) -> list[str]:
    """The options in the order they are shown. Writers tend to put the correct one
    first, so they are shuffled; True/False and Yes/No keep their usual order. An order
    question is never shown already in the correct order."""
    options = list(question.options)
    keys = sorted(option.casefold() for option in options)
    for fixed in FIXED_ORDERS:
        if keys == sorted(fixed):
            return sorted(options, key=lambda option: fixed.index(option.casefold()))
    if len(set(options)) < 2:
        return options
    rng.shuffle(options)
    while question.format == "order" and options == question.correct_options:
        rng.shuffle(options)
    return options


def correct_positions(question: PoolQuestion, shown: list[str]) -> list[int]:
    """Positions of the correct options in the shown order. For order questions in the
    correct order; for the others ascending."""
    if question.format == "order":
        return [shown.index(option) for option in question.correct_options]
    return [i for i, option in enumerate(shown) if option in question.correct_options]
