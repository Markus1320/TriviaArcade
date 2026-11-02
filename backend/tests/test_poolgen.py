"""The question pool generator: critic and solver parsing, the pool index and the pipeline."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.game.matcher import normalize_answer
from app.graph.model import GraphEdge, GraphNode, QuestionSeed
from app.llm.client import LLMError, LLMRateLimitError
from app.llm.critic import QuestionCritic, parse_critic_verdict
from app.llm.critic_prompt import PROMPT as CRITIC_PROMPT
from app.llm.generator import GeneratedQuestion, QuestionGenerator, parse_generated_question
from app.llm.solver import BlindSolver, parse_solver_answers
from app.llm.solver_prompt import PROMPT as SOLVER_PROMPT
from poolgen.index import PoolIndex, answer_aliases, mentioned_entities
from poolgen.pipeline import CountingClient, PoolPipeline, UsageLimitReached, solver_miss
from poolgen.records import (
    PoolQuestion,
    Rejection,
    append_record,
    pool_path,
    read_records,
    rejected_path,
)
from tests.llm_fakes import ListCallLogger, ScriptedClient, real_prompt

FRANCE = GraphNode("Q142", "France", "country", aliases=("Frankreich",))
PARIS = GraphNode("Q90", "Paris", "city", aliases=("Paname",))
SEED = QuestionSeed(
    start=FRANCE, nodes=(FRANCE, PARIS), edges=(GraphEdge("Q142", "CAPITAL", "Q90"),)
)
NOW = datetime(2026, 11, 2, tzinfo=UTC)


def free(**overrides: Any) -> str:
    data: dict[str, Any] = {
        "format": "free",
        "question": "Which city is the capital of France?",
        "expected_answer": "Paris",
        "accepted_answers": [],
        "explanation": "Paris is the capital of France.",
    }
    data.update(overrides)
    return json.dumps(data)


def single(**overrides: Any) -> str:
    data: dict[str, Any] = {
        "format": "single",
        "question": "Which of these cities is the capital of France?",
        "options": ["Lyon", "Paris", "Marseille"],
        "correct_options": ["Paris"],
        "explanation": "Paris is the capital of France.",
    }
    data.update(overrides)
    return json.dumps(data)


def verdict(kind: str, feedback: str = "") -> str:
    return json.dumps({"verdict": kind, "feedback": feedback})


def answers(*items: str) -> str:
    return json.dumps({"answers": list(items)})


def make_pipeline(
    outputs: list[str | LLMError], index: PoolIndex | None = None
) -> tuple[PoolPipeline, ScriptedClient]:
    scripted = ScriptedClient(outputs)
    client = CountingClient(scripted)
    logger = ListCallLogger()
    generator = QuestionGenerator(
        client, "gen", real_prompt("generate_question"), logger, think=True
    )
    pipeline = PoolPipeline(
        generator,
        QuestionCritic(client, "critic", CRITIC_PROMPT, logger),
        BlindSolver(client, "critic", SOLVER_PROMPT, logger),
        index or PoolIndex(),
        client,
        generator_model="gen",
        clock=lambda: NOW,
    )
    return pipeline, scripted


# Parsing


def test_critic_verdict_needs_feedback_unless_approved() -> None:
    assert parse_critic_verdict(verdict("approve")).verdict == "approve"
    assert parse_critic_verdict("```json\n" + verdict("revise", " fix it ") + "\n```").feedback == (
        "fix it"
    )
    with pytest.raises(ValueError):
        parse_critic_verdict(verdict("reject"))
    with pytest.raises(ValueError):
        parse_critic_verdict(verdict("maybe", "hm"))


def test_solver_answers_are_trimmed_and_unique() -> None:
    assert parse_solver_answers(answers(" Paris ", "", "Paris", "Paname")) == ["Paris", "Paname"]
    with pytest.raises(ValueError):
        parse_solver_answers('{"answer": "Paris"}')


def test_normalize_answer_ignores_case_accents_punctuation_and_articles() -> None:
    assert normalize_answer("  The Beatles!") == "beatles"
    assert normalize_answer("Zürich") == normalize_answer("zurich")
    assert normalize_answer("Straße") == "strasse"
    assert normalize_answer("Der Rhein") == "rhein"


def test_solver_miss() -> None:
    question = parse_generated_question(free(accepted_answers=["Paname"]))
    assert solver_miss(question, ["paname"]) is None
    assert solver_miss(question, ["Lyon"]) is not None
    choice = parse_generated_question(single())
    assert solver_miss(choice, ["Paris"]) is None
    assert solver_miss(choice, ["Paris", "Lyon"]) is not None
    order = parse_generated_question(
        single(
            format="order",
            question="Sort these cities by population, largest first.",
            options=["Lyon", "Paris", "Marseille"],
            correct_options=["Paris", "Marseille", "Lyon"],
        )
    )
    assert solver_miss(order, ["Paris", "Marseille", "Lyon"]) is None
    assert solver_miss(order, ["Paris", "Lyon", "Marseille"]) is not None


# Index


def test_mentioned_entities_and_answer_aliases() -> None:
    question = parse_generated_question(free(question="What is the capital of Frankreich?"))
    assert mentioned_entities(SEED, question) == ["Q142", "Q90"]
    assert answer_aliases(SEED, question) == ["Paris", "Paname"]
    assert answer_aliases(SEED, parse_generated_question(single())) == []


def test_index_tracks_starts_related_questions_and_answers(tmp_path: Path) -> None:
    pipeline, _ = make_pipeline([free(), verdict("approve"), answers("Paris")])
    record = pipeline.build(SEED, "en")
    assert isinstance(record, PoolQuestion)
    append_record(pool_path(tmp_path, "en"), record)
    technical = Rejection(
        language="en",
        created_at=NOW,
        start_entity="Q1",
        start_type="x",
        entities=["Q1"],
        facts="",
        reason="critic failed: timeout",
        technical=True,
        rounds=[],
        seconds=1,
        calls=1,
    )
    append_record(rejected_path(tmp_path, "en"), technical)
    append_record(
        rejected_path(tmp_path, "en"),
        technical.model_copy(update={"start_entity": "Q2", "technical": False}),
    )

    index = PoolIndex.build(
        read_records(pool_path(tmp_path, "en"), PoolQuestion),
        read_records(rejected_path(tmp_path, "en"), Rejection),
    )
    # A technical failure leaves the start free for a later walk.
    assert index.used_starts == {"Q142", "Q2"}
    assert index.related(["Q90"]) == ["Which city is the capital of France? [Paris]"]
    assert index.answer_uses(parse_generated_question(free(expected_answer="paris"))) == 1


# Pipeline


def test_approved_and_solved_question_is_accepted() -> None:
    pipeline, client = make_pipeline([free(), verdict("approve"), answers("Paris", "Paname")])
    record = pipeline.build(SEED, "en")
    assert isinstance(record, PoolQuestion)
    assert record.solver_answers == ["Paris", "Paname"]
    assert record.graph_aliases == ["Paris", "Paname"]
    assert record.calls == 3
    assert [r.verdict for r in record.rounds] == ["approve"]
    assert client.requests[0].think is True
    assert client.requests[1].think == "high"
    # The critic sees the draft without the writer's notes.
    assert '"topic"' not in client.requests[1].user


def test_revision_passes_feedback_to_the_writer() -> None:
    pipeline, client = make_pipeline(
        [
            free(),
            verdict("revise", "Too easy, ask about something else."),
            single(),
            verdict("approve"),
            answers("Paris"),
        ]
    )
    record = pipeline.build(SEED, "en")
    assert isinstance(record, PoolQuestion)
    assert record.question.format == "single"
    assert [r.verdict for r in record.rounds] == ["revise", "approve"]
    assert "Too easy, ask about something else." in client.requests[2].user
    assert "Your previous draft" in client.requests[2].user


def test_critic_reject_ends_the_walk() -> None:
    pipeline, _ = make_pipeline([free(), verdict("reject", "Nothing good here.")])
    record = pipeline.build(SEED, "en")
    assert isinstance(record, Rejection)
    assert record.reason == "critic rejected: Nothing good here."
    assert not record.technical


def test_rejected_after_max_rounds() -> None:
    outputs: list[str | LLMError] = []
    for _ in range(3):
        outputs += [free(), verdict("revise", "Still wrong.")]
    pipeline, _ = make_pipeline(outputs)
    record = pipeline.build(SEED, "en")
    assert isinstance(record, Rejection)
    assert record.reason == "not approved after 3 drafts"
    assert len(record.rounds) == 3


def test_blind_solve_miss_rejects() -> None:
    pipeline, _ = make_pipeline([single(), verdict("approve"), answers("Lyon")])
    record = pipeline.build(SEED, "en")
    assert isinstance(record, Rejection)
    assert record.reason.startswith("blind solve: picked other options")


def test_overused_answer_goes_back_to_the_writer_without_the_critic() -> None:
    index = PoolIndex()
    pipeline, _ = make_pipeline([free(), verdict("approve"), answers("Paris")], index)
    first = pipeline.build(SEED, "en")
    assert isinstance(first, PoolQuestion)
    index.add(first)
    index.add(first)
    pipeline, client = make_pipeline(
        [free(), single(), verdict("approve"), answers("Paris")], index
    )
    record = pipeline.build(SEED, "en")
    assert isinstance(record, PoolQuestion)
    assert [r.verdict for r in record.rounds] == ["code", "approve"]
    assert "already the answer of 2 questions" in client.requests[1].user
    # Existing questions about the walk's entities are shown to the writer.
    assert "Questions that already exist" in client.requests[0].user


def test_technical_failure_is_marked() -> None:
    pipeline, _ = make_pipeline([free(), LLMError("timeout"), LLMError("timeout")])
    record = pipeline.build(SEED, "en")
    assert isinstance(record, Rejection)
    assert record.technical
    assert record.reason.startswith("critic failed")


def test_usage_limit_stops_the_walk_without_retry() -> None:
    pipeline, client = make_pipeline([LLMRateLimitError("limit"), free()])
    with pytest.raises(UsageLimitReached):
        pipeline.build(SEED, "en")
    assert len(client.requests) == 1


def test_records_survive_a_round_trip(tmp_path: Path) -> None:
    pipeline, _ = make_pipeline([free(), verdict("approve"), answers("Paris")])
    record = pipeline.build(SEED, "en")
    path = tmp_path / "pool" / "en.jsonl"
    append_record(path, record)
    append_record(path, record)
    loaded = list(read_records(path, PoolQuestion))
    assert loaded == [record, record]
    assert isinstance(loaded[0].question, GeneratedQuestion)
