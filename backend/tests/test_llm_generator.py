import json
from typing import Any

import pytest

from app.graph.model import GraphEdge, GraphNode, QuestionSeed
from app.llm.client import LLMError
from app.llm.generator import (
    QUESTION_SCHEMA,
    GeneratedQuestion,
    QuestionGenerationError,
    QuestionGenerator,
    parse_generated_question,
)
from tests.llm_fakes import ListCallLogger, ScriptedClient, real_prompt

FRANCE = GraphNode("Q142", "France", "country", "country in Western Europe", ("Frankreich",))
PARIS = GraphNode("Q90", "Paris", "city", facts={"population": 2100000, "population_year": 2023})
SEED = QuestionSeed(
    start=FRANCE, nodes=(FRANCE, PARIS), edges=(GraphEdge("Q142", "CAPITAL", "Q90"),)
)


def output(**overrides: Any) -> str:
    data: dict[str, Any] = {
        "question": "Which city is the capital of France?",
        "expected_answer": "Paris",
        "accepted_answers": ["Paname", " paris ", ""],
        "numeric_range": None,
    }
    data.update(overrides)
    return json.dumps(data)


def make_generator(client: ScriptedClient, logger: ListCallLogger) -> QuestionGenerator:
    return QuestionGenerator(client, "gen-model", real_prompt("generate_question"), logger)


# Parsing and validation


def test_parse_valid_output_cleans_accepted_answers() -> None:
    question = parse_generated_question(output())
    assert question.question == "Which city is the capital of France?"
    assert question.expected_answer == "Paris"
    # duplicate of the expected answer and the empty entry are removed
    assert question.accepted_answers == ["Paname"]
    assert question.numeric_range is None


def test_parse_numeric_question() -> None:
    question = parse_generated_question(
        output(
            question="Roughly how many people live in Paris?",
            expected_answer="about 2.1 million",
            accepted_answers=[],
            numeric_range={"min": 1800000, "max": 2400000, "unit": "people"},
        )
    )
    assert question.numeric_range is not None
    assert question.numeric_range.min == 1800000


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "not valid JSON"),
        ('{"question": "Which city?"}', "does not match the schema"),
        (output(expected_answer=""), "does not match the schema"),
        (output(question="Short?"), "does not match the schema"),
        (output(extra="field"), "does not match the schema"),
        (
            output(numeric_range={"min": 10, "max": 5, "unit": "km"}),
            "must not exceed",
        ),
        (output(question="Is Paris the capital city of France?"), "gives away the expected answer"),
        (json.dumps(["a", "list"]), "does not match the schema"),
    ],
)
def test_parse_rejects_invalid_output(raw: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_generated_question(raw)


def test_schema_matches_model_fields() -> None:
    assert set(QUESTION_SCHEMA["properties"]) == set(GeneratedQuestion.model_fields)
    assert set(QUESTION_SCHEMA["required"]) == set(GeneratedQuestion.model_fields)


# Generator calls


def test_generate_sends_facts_and_schema_and_logs_call() -> None:
    client = ScriptedClient([output()])
    logger = ListCallLogger()
    question = make_generator(client, logger).generate(SEED)

    assert question.expected_answer == "Paris"
    request = client.requests[0]
    assert request.model == "gen-model"
    assert request.json_schema == QUESTION_SCHEMA
    assert "France -- capital --> Paris" in request.user
    assert "$facts" not in request.user
    assert [(r.purpose, r.attempt, r.error) for r in logger.records] == [("generate", 1, None)]
    assert logger.records[0].parsed["expected_answer"] == "Paris"
    assert logger.records[0].request["user"] == request.user


def test_generate_retries_once_after_invalid_output() -> None:
    client = ScriptedClient(["{broken", output()])
    logger = ListCallLogger()
    question = make_generator(client, logger).generate(SEED)

    assert question.expected_answer == "Paris"
    assert [r.attempt for r in logger.records] == [1, 2]
    assert logger.records[0].error is not None
    assert logger.records[0].raw_output == "{broken"
    assert logger.records[0].parsed is None


def test_generate_raises_after_two_failures() -> None:
    client = ScriptedClient([LLMError("HTTP 503"), "still not json"])
    logger = ListCallLogger()
    with pytest.raises(QuestionGenerationError, match="HTTP 503"):
        make_generator(client, logger).generate(SEED)
    assert len(logger.records) == 2
    assert logger.records[0].raw_output is None
