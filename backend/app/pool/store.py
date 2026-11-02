"""Reads the pool files and picks questions from them.

The files are read again whenever one changes, because the generator may still be
appending to them while the game runs. A half written last line is skipped until the next
read.
"""

import logging
import random
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.game.matcher import normalize_answer
from app.llm.generator import GeneratedQuestion
from app.pool.records import PoolQuestion, pool_path

logger = logging.getLogger(__name__)

# Least recently asked questions are picked at random among this many of the oldest.
LEAST_RECENT_CHOICES = 50


@dataclass(frozen=True)
class PoolEntry:
    id: str
    language: str
    start_entity: str
    start_type: str
    facts: str
    question: GeneratedQuestion
    # Every other form a typed answer may take: the writer's accepted answers and the blind
    # solver's answers, without the expected answer. Empty for choice questions.
    other_answers: tuple[str, ...]
    generator_model: str
    prompt: str


def to_entry(record: PoolQuestion) -> PoolEntry:
    question = record.question
    other: list[str] = []
    if not question.is_choice:
        seen = {normalize_answer(question.expected_answer)}
        for answer in [*question.accepted_answers, *record.solver_answers]:
            form = normalize_answer(answer)
            if form and form not in seen:
                seen.add(form)
                other.append(answer)
    return PoolEntry(
        id=record.id,
        language=record.language,
        start_entity=record.start_entity,
        start_type=record.start_type,
        facts=record.facts,
        question=question,
        other_answers=tuple(other),
        generator_model=record.generator_model,
        prompt=record.prompt,
    )


class PoolStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._cache: dict[str, tuple[tuple[float, int], list[PoolEntry]]] = {}

    def entries(self, language: str) -> list[PoolEntry]:
        path = pool_path(self._directory, language)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return []
        version = (stat.st_mtime, stat.st_size)
        cached = self._cache.get(language)
        if cached is not None and cached[0] == version:
            return cached[1]
        entries = _read(path)
        self._cache[language] = (version, entries)
        return entries


def _read(path: Path) -> list[PoolEntry]:
    entries: list[PoolEntry] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                record = PoolQuestion.model_validate_json(line)
            except ValidationError:
                logger.warning("Skipping unreadable line %d of %s", number, path)
                continue
            if record.id not in seen:
                seen.add(record.id)
                entries.append(to_entry(record))
    return entries


def pick_unasked(
    entries: Sequence[PoolEntry],
    asked: Collection[str],
    blocked_starts: Collection[str],
    rng: random.Random,
) -> PoolEntry | None:
    """A question no run has had yet. As with live questions, an entity type is picked
    first, uniformly, then a question of that type, so every type keeps its share."""
    by_type: dict[str, list[PoolEntry]] = {}
    for entry in entries:
        if entry.id not in asked and entry.start_entity not in blocked_starts:
            by_type.setdefault(entry.start_type, []).append(entry)
    if not by_type:
        return None
    return rng.choice(by_type[rng.choice(sorted(by_type))])


def pick_least_recent(
    entries: Sequence[PoolEntry],
    last_asked: Mapping[str, int],
    run_ids: Collection[str],
    blocked_starts: Collection[str],
    rng: random.Random,
) -> PoolEntry | None:
    """When every question has been asked: one of those asked longest ago (last_asked maps
    a question to a number that grows with time). Never one the run already had; the
    blocked starts are given up when nothing else is left."""
    candidates = [e for e in entries if e.id not in run_ids]
    unblocked = [e for e in candidates if e.start_entity not in blocked_starts]
    candidates = unblocked or candidates
    if not candidates:
        return None
    candidates.sort(key=lambda entry: last_asked.get(entry.id, -1))
    return rng.choice(candidates[:LEAST_RECENT_CHOICES])
