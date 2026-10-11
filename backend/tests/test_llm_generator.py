import json
import random
from typing import Any

import pytest

from app.graph.model import GraphEdge, GraphNode, QuestionSeed
from app.llm.client import LLMError
from app.llm.generator import (
    QUESTION_SCHEMA,
    GeneratedQuestion,
    QuestionGenerationError,
    QuestionGenerator,
    find_giveaway,
    parse_generated_question,
    shuffle_options,
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
        "explanation": " Paris has been the capital of France for centuries. ",
    }
    data.update(overrides)
    return json.dumps(data)


def choice(**overrides: Any) -> str:
    data: dict[str, Any] = {
        "format": "single",
        "question": "Which of these cities is the capital of France?",
        "options": ["Lyon", " Paris ", "Marseille"],
        "correct_options": ["paris"],
        "explanation": "Paris is the capital of France.",
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
    assert question.explanation == "Paris has been the capital of France for centuries."


def test_explanation_is_optional() -> None:
    data = json.loads(output())
    del data["explanation"]
    assert parse_generated_question(json.dumps(data)).explanation == ""


@pytest.mark.parametrize(
    "wrap",
    [
        "```json\n{}\n```",  # seen from gemma4:31b on the Ollama cloud API
        "```\n{}\n```",
        "  ```JSON {} ```  ",
        "Here is your question:\n{}\nGood luck!",
    ],
)
def test_parse_tolerates_code_fences_and_surrounding_text(wrap: str) -> None:
    question = parse_generated_question(wrap.replace("{}", output()))
    assert question.expected_answer == "Paris"


def test_generate_accepts_fenced_output() -> None:
    logger = ListCallLogger()
    raw = f"```json\n{output()}\n```"
    question = make_generator(ScriptedClient([raw]), logger).generate(SEED)
    assert question.expected_answer == "Paris"
    assert logger.records[0].raw_output == raw  # logged unchanged


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("not json", "not valid JSON"),
        ("```json\n{broken\n```", "not valid JSON"),
        ('{"question": "Which city?"}', "needs an expected_answer"),
        (output(expected_answer=""), "needs an expected_answer"),
        (output(format="essay"), "does not match the schema"),
        (output(options=["Paris", "Lyon"]), "must not have options"),
        # Giveaways: the answer, or an accepted form of it, is part of the question.
        (output(question="Is Paris the capital of France, or is it Lyon?"), "its own answer"),
        (output(accepted_answers=["Capital of France"]), "its own answer"),
        (choice(options=["Paris"]), "needs 2 to 5 options"),
        (choice(options=["Paris", "paris ", "Lyon"]), "must be distinct"),
        (choice(options=["Paris", "", "Lyon"]), "1 to 80 characters"),
        (choice(correct_options=["Nice"]), "not among the options"),
        (choice(options=["Lyon", "Paris", "All of the above"]), "must not combine"),
        (choice(options=["Lyon", "Paris", "Both Lyon and Paris"]), "must not combine"),
        (choice(options=["Lyon", "Paris", "Keine der genannten"]), "must not combine"),
        (choice(correct_options=[]), "exactly one correct"),
        (choice(correct_options=["Paris", "Lyon"]), "exactly one correct"),
        (choice(format="multiple", correct_options=["Paris"]), "at least two correct"),
        (
            choice(question="Which of these, like Paris, is the capital of France?"),
            "names only the correct option",
        ),
        (
            choice(format="multiple", correct_options=["Paris", "Lyon", "Marseille"]),
            "at least two correct",
        ),
        (output(question="Short?"), "does not match the schema"),
        (output(extra="field"), "does not match the schema"),
        (json.dumps(["a", "list"]), "does not match the schema"),
    ],
)
def test_parse_rejects_invalid_output(raw: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_generated_question(raw)


def test_schema_matches_model_fields() -> None:
    assert set(QUESTION_SCHEMA["properties"]) == set(GeneratedQuestion.model_fields)
    # The other fields depend on the format.
    assert set(QUESTION_SCHEMA["required"]) == {"format", "question", "explanation"}


def test_format_defaults_to_free() -> None:
    question = parse_generated_question(output())
    assert question.format == "free"
    assert not question.is_choice


def test_parse_single_choice() -> None:
    question = parse_generated_question(choice())
    assert question.is_choice
    assert question.options == ["Lyon", "Paris", "Marseille"]
    # Matched to the option's own spelling; expected_answer is derived for display.
    assert question.correct_options == ["Paris"]
    assert question.correct_indices == [1]
    assert question.expected_answer == "Paris"


def test_parse_multiple_choice() -> None:
    question = parse_generated_question(
        choice(
            format="multiple",
            question="Which of these cities lie in France?",
            options=["Lyon", "Paris", "Geneva", "Turin"],
            correct_options=["Paris", "Lyon"],
        )
    )
    assert question.correct_indices == [0, 1]
    assert question.expected_answer == "Lyon, Paris"


def test_choice_question_may_name_its_answer() -> None:
    raw = choice(
        question="True or false: Paris is the capital of France.",
        options=["True", "False"],
        correct_options=["True"],
    )
    assert parse_generated_question(raw).expected_answer == "True"


@pytest.mark.parametrize(
    ("question", "answers", "found"),
    [
        ("Where did the French Revolution take place?", ["France"], None),
        ("What was the language of the French Empire?", ["French"], "French"),
        ("Which river flows through Vienna?", ["Danube", "vienna"], "vienna"),
        ("Who founded the Mongol Empire?", ["Mongol  empire!"], "Mongol  empire!"),
        # Short answers would match by accident.
        ("Which UN agency is based in Paris?", ["UN"], None),
        ("Sort these, oldest first: Google, Apple.", ["Apple, Google"], None),
    ],
)
def test_find_giveaway(question: str, answers: list[str], found: str | None) -> None:
    assert find_giveaway(question, answers) == found


def test_shuffle_keeps_the_correct_options() -> None:
    question = parse_generated_question(
        choice(options=["Paris", "Lyon", "Marseille", "Nice", "Lille"], correct_options=["Paris"])
    )
    orders = {tuple(shuffle_options(question, random.Random(seed)).options) for seed in range(20)}
    assert len(orders) > 1
    for seed in range(20):
        shuffled = shuffle_options(question, random.Random(seed))
        assert sorted(shuffled.options) == sorted(question.options)
        assert shuffled.options[shuffled.correct_indices[0]] == "Paris"


def test_shuffle_keeps_true_false_in_order() -> None:
    question = parse_generated_question(
        choice(
            question="True or false: Lyon is the capital of France.",
            options=["False", "True"],
            correct_options=["False"],
        )
    )
    for seed in range(5):
        shuffled = shuffle_options(question, random.Random(seed))
        assert shuffled.options == ["True", "False"]
        assert shuffled.correct_indices == [1]


def test_shuffle_leaves_free_questions_alone() -> None:
    question = parse_generated_question(output())
    assert shuffle_options(question, random.Random(1)) == question


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
    assert "If you write a true or false question, the claim must be" in request.user
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


def test_generate_asks_in_the_language_of_the_run() -> None:
    client = ScriptedClient([output()])
    make_generator(client, ListCallLogger()).generate(SEED, language="de")
    request = client.requests[0]
    assert "auf Deutsch" in request.user
    assert "France -- capital --> Paris" in request.user
    assert "Wahr-oder-falsch-Frage" in request.user


def test_shuffle_keeps_wahr_falsch_in_order() -> None:
    question = parse_generated_question(
        choice(
            question="Wahr oder falsch: Lyon ist die Hauptstadt von Frankreich.",
            options=["Falsch", "Wahr"],
            correct_options=["Falsch"],
        )
    )
    assert shuffle_options(question, random.Random(3)).options == ["Wahr", "Falsch"]


def test_choice_question_may_name_all_its_options() -> None:
    raw = choice(
        question="Which city is larger, Paris or Lyon?",
        options=["Paris", "Lyon"],
        correct_options=["Paris"],
    )
    assert parse_generated_question(raw).expected_answer == "Paris"


def test_true_false_question_may_use_the_word_true() -> None:
    raw = choice(
        question="Is it true that Paris is the capital of France?",
        options=["True", "False"],
        correct_options=["True"],
    )
    assert parse_generated_question(raw).expected_answer == "True"


def test_retry_tells_the_model_why_it_was_rejected() -> None:
    giveaway = output(question="Is Paris the capital of France, or is it Lyon?")
    client = ScriptedClient([giveaway, output()])
    logger = ListCallLogger()
    make_generator(client, logger).generate(SEED)
    first, second = client.requests
    assert "previous attempt was rejected" not in first.user
    assert second.user.startswith(first.user)
    assert "previous attempt was rejected: the question contains its own answer" in second.user
    # The log shows what was actually sent in each attempt.
    assert logger.records[1].request["user"] == second.user


def test_retry_after_a_technical_failure_repeats_the_request() -> None:
    client = ScriptedClient([LLMError("HTTP 503"), output()])
    make_generator(client, ListCallLogger()).generate(SEED)
    assert client.requests[0].user == client.requests[1].user
