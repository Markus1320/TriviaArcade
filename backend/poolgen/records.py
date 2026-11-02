"""What the question pool stores: one JSON object per line, accepted and rejected walks apart.

<dir>/<language>.jsonl           accepted questions (the pool)
<dir>/<language>.rejected.jsonl  walks that gave no question, so their starts are not
                                 tried again and the reasons can be reviewed
"""

import hashlib
import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.llm.generator import GeneratedQuestion

# Where the generator writes (gitignored data/pool, mounted into the container). Finished
# pools are copied into the repository's pool/ folder and committed.
DEFAULT_DIR = os.environ.get("POOL_DIR", "../data/pool")

RoundVerdict = Literal["approve", "revise", "reject", "code"]


class Round(BaseModel):
    """One draft of the writer and what happened to it: the critic's verdict, or "code"
    when a code check sent it back before the critic saw it."""

    question: GeneratedQuestion
    verdict: RoundVerdict
    feedback: str = ""


class PoolQuestion(BaseModel):
    id: str
    language: str
    created_at: datetime
    start_entity: str
    start_type: str
    # Wikidata IDs of every entity of the walk, and of those named in the question, its
    # answers or options (used to find related questions).
    entities: list[str]
    mentioned: list[str]
    facts: str
    question: GeneratedQuestion
    # The blind solver's answers. For free questions every form it would count as correct.
    solver_answers: list[str]
    # Label and aliases of the entity a free question asks for, from the knowledge graph.
    graph_aliases: list[str]
    generator_model: str
    critic_model: str
    # The writer's request for the accepted draft (the system prompt is the same for all).
    prompt: str
    rounds: list[Round]
    seconds: float
    calls: int


class Rejection(BaseModel):
    language: str
    created_at: datetime
    start_entity: str
    start_type: str
    entities: list[str]
    facts: str
    reason: str
    # A call failed (no valid reply after retries) instead of the content falling short.
    # The start entity stays available for a later walk.
    technical: bool = False
    rounds: list[Round]
    seconds: float
    calls: int


def question_id(language: str, text: str) -> str:
    return hashlib.sha1(f"{language}\n{text}".encode()).hexdigest()[:12]


def pool_path(directory: Path, language: str) -> Path:
    return directory / f"{language}.jsonl"


def rejected_path(directory: Path, language: str) -> Path:
    return directory / f"{language}.rejected.jsonl"


def read_records[Record: (PoolQuestion, Rejection)](
    path: Path, model: type[Record]
) -> Iterator[Record]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield model.model_validate_json(line)


def append_record(path: Path, record: PoolQuestion | Rejection) -> None:
    """One line per record, flushed at once, so an interrupted run keeps what it made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(record.model_dump_json() + "\n")
