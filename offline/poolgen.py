"""Fill the question pool of one language: from walks through the graph to questions.

    docker compose --profile offline run --rm poolgen --language en --walks 100

For every walk:
1. The writer drafts a question from the walk's facts, thinking first. Its request also
   lists the pool's questions about the walk's entities ("do not ask these again").
2. Code check: the same typed answer may be in the pool at most --answer-cap times;
   otherwise the draft goes back to the writer with a note.
3. The critic approves, asks for a revision (back to 1 with its feedback) or rejects.
   At most --max-rounds drafts.
4. The blind solver answers the approved question without seeing the answer. A choice
   question passes when it picks exactly the correct options, a free question when its
   answers include the expected or an accepted one. Its answers are kept: they are the
   forms a typed answer may take, so the game can check answers without an LLM.

Every walk ends in one line in pool/<language>.jsonl (accepted) or
pool/<language>.rejected.jsonl, written at once, so a run can stop any time and the next
one continues where the pool stands. Every start entity is walked once per pool; only a
technical failure leaves it free for a later walk. When the provider's usage limit is
reached (HTTP 429), the walk in progress is dropped and the run waits --wait-hours.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from collections import Counter
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from game.matcher import normalize_answer
from offline import llm
from offline.importer.settings import neo4j_connection
from offline.llm import Chat, LLMError, UsageLimitReached
from offline.prompts import critic as critic_prompt
from offline.prompts import solver as solver_prompt
from offline.prompts import writer as writer_prompt
from offline.questions import (
    NOTE_FIELDS,
    QUESTION_SCHEMA,
    Question,
    check_question,
    find_giveaway,
    shuffled,
)
from offline.walk import NoWalkError, Walk, facts_text, random_walk

WRITER_TEMPERATURE = 0.8
# Walks failing in a row for technical reasons before the run waits as for a usage limit.
MAX_FAILURES_IN_A_ROW = 5
# Pool questions about the walk's entities shown to the writer and the critic.
RELATED_LIMIT = 10
LANGUAGE_NAMES = {"en": "English", "de": "German"}

EXISTING_NOTE = (
    "Questions that already exist about these entities. Do not ask their facts again, in "
    "any format or wording; ask about something different:\n{questions}"
)
REVISION_NOTE = (
    "Your previous draft:\n{draft}\n\nA strict editor reviewed it:\n{feedback}\n\n"
    "Write an improved question that follows the feedback. You may change the format or "
    "ask about another fact."
)
ANSWER_USED_NOTE = (
    "The answer {answer!r} is already the answer of {uses} questions in the pool. Ask about "
    "something with another answer."
)

CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "revise", "reject"]},
        "feedback": {"type": "string"},
    },
    "required": ["verdict", "feedback"],
}
SOLVER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answers": {"type": "array", "items": {"type": "string"}}},
    "required": ["answers"],
}


# --- The pool files ---


def pool_file(directory: Path, language: str) -> Path:
    return directory / f"{language}.jsonl"


def rejected_file(directory: Path, language: str) -> Path:
    return directory / f"{language}.rejected.jsonl"


def read_records(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield json.loads(line)


def append_record(path: Path, record: dict[str, Any]) -> None:
    """One line per record, written at once, so an interrupted run keeps what it made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def question_id(language: str, text: str) -> str:
    return hashlib.sha1(f"{language}\n{text}".encode()).hexdigest()[:12]


def timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class PoolIndex:
    """What the pool already holds, so new questions do not repeat it: the start entities
    walked, the questions about each entity, and how often each typed answer is used."""

    def __init__(self) -> None:
        self.used_starts: set[str] = set()
        self.accepted = 0
        self.by_entity: dict[str, list[str]] = {}
        self.answers: Counter[str] = Counter()

    def add(self, record: dict[str, Any]) -> None:
        question = record["question"]
        self.accepted += 1
        self.used_starts.add(record["start_entity"])
        summary = f"{question['question']} [{question['expected_answer']}]"
        for entity in record["mentioned"]:
            self.by_entity.setdefault(entity, []).append(summary)
        if question["format"] == "free":
            self.answers[normalize_answer(question["expected_answer"])] += 1

    def add_rejection(self, record: dict[str, Any]) -> None:
        if not record.get("technical"):
            self.used_starts.add(record["start_entity"])

    def related(self, entity_ids: Sequence[str]) -> list[str]:
        """Pool questions that name one of these entities, the start entity's first."""
        found: list[str] = []
        for entity in entity_ids:
            for summary in self.by_entity.get(entity, []):
                if summary not in found:
                    found.append(summary)
        return found[:RELATED_LIMIT]

    def answer_uses(self, question: Question) -> int:
        if question.is_choice:
            return 0
        return self.answers[normalize_answer(question.expected_answer)]


def load_index(directory: Path, language: str) -> PoolIndex:
    index = PoolIndex()
    for record in read_records(pool_file(directory, language)):
        index.add(record)
    for record in read_records(rejected_file(directory, language)):
        index.add_rejection(record)
    return index


# --- The three roles ---


def write(
    chat: Chat, model: str, walk: Walk, language: str, context: str, rng: random.Random
) -> tuple[Question, str]:
    """A checked draft from the writer, and the request that produced it."""
    user = writer_prompt.USER_TEMPLATES[language].substitute(
        facts=facts_text(walk),
        examples=writer_prompt.pick_examples(rng, language),
        true_false_hint=writer_prompt.pick_true_false_hint(rng, language),
    )
    if context:
        user += "\n\n" + context
    question, prompt = llm.ask(
        chat,
        model=model,
        system=writer_prompt.SYSTEM_PROMPT,
        user=user,
        check=check_question,
        schema=QUESTION_SCHEMA,
        think=True,
        temperature=WRITER_TEMPERATURE,
    )
    return shuffled(question, rng), prompt


def review(
    chat: Chat, model: str, question: Question, facts: str, existing: list[str], language: str
) -> tuple[str, str]:
    """The critic's verdict ("approve", "revise" or "reject") and its feedback."""
    user = critic_prompt.USER_TEMPLATE.substitute(
        game_language=LANGUAGE_NAMES[language],
        facts=facts,
        existing="\n".join(f"- {q}" for q in existing) if existing else "(none)",
        draft=draft_for_review(question),
    )
    result, _ = llm.ask(
        chat,
        model=model,
        system=critic_prompt.SYSTEM_PROMPT,
        user=user,
        check=check_verdict,
        schema=CRITIC_SCHEMA,
        think="high",
    )
    return result


def check_verdict(data: dict[str, Any]) -> tuple[str, str]:
    verdict, feedback = data.get("verdict"), data.get("feedback", "")
    if verdict not in ("approve", "revise", "reject"):
        raise ValueError(f"the verdict must be approve, revise or reject, not {verdict!r}")
    if not isinstance(feedback, str) or len(feedback) > 2000:
        raise ValueError("the feedback must be a text of at most 2000 characters")
    if verdict != "approve" and not feedback.strip():
        raise ValueError("a revise or reject verdict needs feedback")
    return verdict, feedback.strip()


def draft_for_review(question: Question) -> str:
    """The draft as JSON without the writer's notes, which the critic judges unseen."""
    data = question.model_dump(exclude=set(NOTE_FIELDS))
    if question.is_choice:
        del data["expected_answer"], data["accepted_answers"]
    else:
        del data["options"], data["correct_options"]
    return json.dumps(data, ensure_ascii=False, indent=1)


def solve(chat: Chat, model: str, question: Question, language: str) -> list[str]:
    """The blind solver's answers to the question, without seeing its answer."""
    options = "".join(f"- {option}\n" for option in question.options)
    user = solver_prompt.USER_TEMPLATE.substitute(
        game_language=LANGUAGE_NAMES[language],
        format=question.format,
        question=question.question,
        options=f"Options:\n{options}" if options else "",
    )
    answers, _ = llm.ask(
        chat,
        model=model,
        system=solver_prompt.SYSTEM_PROMPT,
        user=user,
        check=check_answers,
        schema=SOLVER_SCHEMA,
        think="high",
    )
    return answers


def check_answers(data: dict[str, Any]) -> list[str]:
    answers = data.get("answers")
    if not isinstance(answers, list) or len(answers) > 100:
        raise ValueError("answers must be a list of at most 100 texts")
    found: list[str] = []
    for answer in answers:
        text = str(answer).strip()
        if text and text not in found:
            found.append(text)
    return found


def solver_miss(question: Question, solved: Sequence[str]) -> str | None:
    """Why the blind solver's answers do not confirm the question, or None if they do."""
    found = [normalize_answer(answer) for answer in solved]
    if question.format == "order":
        expected = [normalize_answer(option) for option in question.correct_options]
        return None if found == expected else "sorted differently"
    if question.is_choice:
        expected_set = {normalize_answer(option) for option in question.correct_options}
        return None if set(found) == expected_set else "picked other options"
    answers = [question.expected_answer, *question.accepted_answers]
    if any(normalize_answer(answer) in found for answer in answers):
        return None
    return "the expected answer is not among its answers"


# --- One walk, start to end ---


def make_question(
    chat: Chat,
    walk: Walk,
    language: str,
    index: PoolIndex,
    *,
    writer_model: str,
    critic_model: str,
    rng: random.Random,
    max_rounds: int = 3,
    answer_cap: int = 2,
) -> tuple[bool, dict[str, Any]]:
    """The pool record of one walk: (True, accepted question) or (False, rejection).
    Raises UsageLimitReached when the provider refuses calls."""
    started = time.perf_counter()
    calls = 0

    def counted_chat(body: dict[str, Any]) -> str:
        nonlocal calls
        calls += 1
        return chat(body)

    facts = facts_text(walk)
    entity_ids = [node.wikidata_id for node in walk.nodes]
    existing = index.related(entity_ids)
    rounds: list[dict[str, Any]] = []

    def rejection(reason: str, technical: bool = False) -> tuple[bool, dict[str, Any]]:
        return False, {
            "language": language,
            "created_at": timestamp(),
            "start_entity": walk.start.wikidata_id,
            "start_type": walk.start.entity_type,
            "entities": entity_ids,
            "facts": facts,
            "reason": reason,
            # A call failed, the content did not fall short: the start stays free.
            "technical": technical,
            "rounds": rounds,
            "seconds": round(time.perf_counter() - started, 1),
            "calls": calls,
        }

    approved = None
    revision = ""
    for _ in range(max_rounds):
        notes = []
        if existing:
            notes.append(EXISTING_NOTE.format(questions="\n".join(f"- {q}" for q in existing)))
        if revision:
            notes.append(revision)
        context = "\n\n".join(notes)
        try:
            draft, prompt = write(counted_chat, writer_model, walk, language, context, rng)
        except LLMError as error:
            return rejection(f"writer failed: {error}", technical=True)
        uses = index.answer_uses(draft)
        if uses >= answer_cap:
            note = ANSWER_USED_NOTE.format(answer=draft.expected_answer, uses=uses)
            rounds.append({"question": draft.model_dump(), "verdict": "code", "feedback": note})
            revision = REVISION_NOTE.format(draft=draft_for_review(draft), feedback=note)
            continue
        try:
            verdict, feedback = review(counted_chat, critic_model, draft, facts, existing, language)
        except LLMError as error:
            return rejection(f"critic failed: {error}", technical=True)
        rounds.append({"question": draft.model_dump(), "verdict": verdict, "feedback": feedback})
        if verdict == "approve":
            approved = (draft, prompt)
            break
        if verdict == "reject":
            return rejection(f"critic rejected: {feedback}")
        revision = REVISION_NOTE.format(draft=draft_for_review(draft), feedback=feedback)
    if approved is None:
        return rejection(f"not approved after {max_rounds} drafts")

    question, prompt = approved
    try:
        solved = solve(counted_chat, critic_model, question, language)
    except LLMError as error:
        return rejection(f"solver failed: {error}", technical=True)
    miss = solver_miss(question, solved)
    if miss:
        return rejection(f"blind solve: {miss} (solver: {solved})")

    return True, {
        "id": question_id(language, question.question),
        "language": language,
        "created_at": timestamp(),
        "start_entity": walk.start.wikidata_id,
        "start_type": walk.start.entity_type,
        "entities": entity_ids,
        # The walk's entities named in the question, its answers or options.
        "mentioned": mentioned_entities(walk, question),
        "facts": facts,
        "question": question.model_dump(),
        "solver_answers": solved,
        "graph_aliases": answer_aliases(walk, question),
        "generator_model": writer_model,
        "critic_model": critic_model,
        "prompt": prompt,
        "rounds": rounds,
        "seconds": round(time.perf_counter() - started, 1),
        "calls": calls,
    }


def mentioned_entities(walk: Walk, question: Question) -> list[str]:
    text = " ".join(
        [question.question, question.expected_answer, *question.accepted_answers, *question.options]
    )
    return [
        node.wikidata_id
        for node in walk.nodes
        if find_giveaway(text, [node.label, *node.aliases]) is not None
    ]


def answer_aliases(walk: Walk, question: Question) -> list[str]:
    """Label and aliases of the entity a free question asks for, if it is in the walk."""
    if question.is_choice:
        return []
    answers = {normalize_answer(a) for a in [question.expected_answer, *question.accepted_answers]}
    for node in walk.nodes:
        names = [node.label, *node.aliases]
        if any(normalize_answer(name) in answers for name in names):
            return names
    return []


# --- The command line ---


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m offline.poolgen")
    parser.add_argument("--language", choices=sorted(LANGUAGE_NAMES), required=True)
    parser.add_argument("--walks", type=int, required=True, help="walks to process")
    parser.add_argument("--dir", type=Path, default=Path("pool"), help="pool directory")
    parser.add_argument("--seed", type=int, help="random seed for reproducible walks")
    parser.add_argument("--types", help="only start from these entity types, comma separated")
    parser.add_argument("--max-rounds", type=int, default=3, help="drafts per walk")
    parser.add_argument("--answer-cap", type=int, default=2, help="pool uses of a typed answer")
    parser.add_argument("--wait-hours", type=float, default=5.0, help="pause at a usage limit")
    args = parser.parse_args(argv)

    env = os.environ
    missing = [
        name
        for name in ["OLLAMA_BASE_URL", "LLM_GENERATOR_MODEL", "LLM_CRITIC_MODEL"]
        if not env.get(name)
    ]
    if missing:
        print(f"Set {', '.join(missing)} in .env.", file=sys.stderr)
        return 2
    writer_model, critic_model = env["LLM_GENERATOR_MODEL"], env["LLM_CRITIC_MODEL"]
    ollama = llm.Ollama(
        env["OLLAMA_BASE_URL"],
        env.get("OLLAMA_API_KEY", ""),
        # Thinking takes a while.
        timeout_seconds=max(float(env.get("LLM_TIMEOUT_SECONDS", "300")), 300),
    )
    uri, user, password = neo4j_connection()
    driver = GraphDatabase.driver(uri, auth=(user, password))

    index = load_index(args.dir, args.language)
    accepted_path = pool_file(args.dir, args.language)
    rejected_path = rejected_file(args.dir, args.language)
    print(f"Pool {accepted_path}: {index.accepted} questions, {len(index.used_starts)} starts used")

    rng = random.Random(args.seed)
    start_types = [t.strip() for t in args.types.split(",")] if args.types else []
    failures = 0
    walk_number = 0
    try:
        while walk_number < args.walks:
            try:
                walk = random_walk(
                    driver,
                    rng,
                    index.used_starts,
                    min_hops=int(env.get("WALK_MIN_HOPS", "1")),
                    max_hops=int(env.get("WALK_MAX_HOPS", "2")),
                    hub_penalty=float(env.get("WALK_HUB_PENALTY", "0.5")),
                    start_types=start_types,
                )
            except NoWalkError as error:
                print(f"No more walks: {error}")
                break
            try:
                accepted, record = make_question(
                    ollama.chat,
                    walk,
                    args.language,
                    index,
                    writer_model=writer_model,
                    critic_model=critic_model,
                    rng=rng,
                    max_rounds=args.max_rounds,
                    answer_cap=args.answer_cap,
                )
            except UsageLimitReached as error:
                wait(f"usage limit reached ({error})", args.wait_hours)
                continue
            walk_number += 1
            progress = f"[{walk_number}/{args.walks}]"
            usage = f"{record['calls']} calls, {record['seconds']:.0f}s"
            if accepted:
                append_record(accepted_path, record)
                index.add(record)
                failures = 0
                question = record["question"]
                print(
                    f"{progress} ok     {record['start_type']}: {question['format']} "
                    f"{question['question']} ({len(record['rounds'])} drafts, {usage})"
                )
                continue
            append_record(rejected_path, record)
            index.add_rejection(record)
            print(f"{progress} reject {record['start_type']}: {record['reason'][:160]} ({usage})")
            failures = failures + 1 if record["technical"] else 0
            if failures >= MAX_FAILURES_IN_A_ROW:
                wait(f"{failures} technical failures in a row", args.wait_hours)
                failures = 0
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        ollama.close()
        driver.close()
    print(f"Pool {accepted_path}: {index.accepted} questions")
    return 0


def wait(reason: str, hours: float) -> None:
    resume = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + hours * 3600))
    print(f"{reason}; the walk in progress is dropped. Waiting until {resume}.", flush=True)
    time.sleep(hours * 3600)


if __name__ == "__main__":
    sys.exit(main())
