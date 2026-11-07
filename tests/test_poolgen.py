"""Making pool questions, with canned LLM replies instead of a real model.

canned() gives a chat function that returns the given replies in order and remembers
every request it got. No test calls an LLM or Neo4j.
"""

import json
import random
from typing import Any

import pytest

from offline import llm
from offline.llm import LLMError, UsageLimitReached
from offline.poolgen import PoolIndex, make_question, solver_miss
from offline.prompts.writer import EXAMPLES
from offline.questions import Question, check_question, find_giveaway
from offline.walk import Edge, Node, Walk

FRANCE = Node("Q142", "France", "country", aliases=("Frankreich",))
PARIS = Node("Q90", "Paris", "city", aliases=("Paname",))
WALK = Walk(start=FRANCE, nodes=(FRANCE, PARIS), edges=(Edge("Q142", "CAPITAL", "Q90"),))


def canned(*replies: str | Exception) -> tuple[llm.Chat, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []

    def chat(body: dict[str, Any]) -> str:
        sent.append(body)
        reply = replies[len(sent) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply

    return chat, sent


def free(**changes: Any) -> dict[str, Any]:
    return {
        "topic": "the capital of France",
        "format": "free",
        "question": "Which city is the capital of France?",
        "expected_answer": "Paris",
        "accepted_answers": [],
        "explanation": "Paris is the capital of France.",
        **changes,
    }


def single(**changes: Any) -> dict[str, Any]:
    return {
        "format": "single",
        "question": "Which of these cities is the capital of France?",
        "options": ["Lyon", "Paris", "Marseille"],
        "correct_options": ["Paris"],
        "explanation": "Paris is the capital of France.",
        **changes,
    }


def reply(data: dict[str, Any]) -> str:
    return json.dumps(data)


def verdict(kind: str, feedback: str = "") -> str:
    return reply({"verdict": kind, "feedback": feedback})


def answers(*items: str) -> str:
    return reply({"answers": list(items)})


def run(chat: llm.Chat, index: PoolIndex | None = None) -> tuple[bool, dict[str, Any]]:
    return make_question(
        chat,
        WALK,
        "en",
        index or PoolIndex(),
        writer_model="writer",
        critic_model="critic",
        rng=random.Random(1),
    )


def test_approved_question_with_the_solver_forms() -> None:
    chat, sent = canned(reply(free()), verdict("approve"), answers("Paris", "Paname"))
    accepted, record = run(chat)
    assert accepted
    assert record["question"]["expected_answer"] == "Paris"
    assert record["solver_answers"] == ["Paris", "Paname"]
    assert record["mentioned"] == ["Q142", "Q90"]
    assert record["graph_aliases"] == ["Paris", "Paname"]
    assert record["calls"] == 3
    assert [r["verdict"] for r in record["rounds"]] == ["approve"]
    # Writer, critic and solver get their own model; the facts reach writer and critic.
    assert [body["model"] for body in sent] == ["writer", "critic", "critic"]
    assert "France -- capital --> Paris" in record["prompt"]
    assert "France -- capital --> Paris" in sent[1]["messages"][1]["content"]
    # The solver never sees the answer.
    assert "Paris" not in sent[2]["messages"][1]["content"]


def test_a_revision_goes_back_to_the_writer() -> None:
    chat, sent = canned(
        reply(free(explanation="Paris is in France.")),
        verdict("revise", "Say more in the explanation."),
        reply(free()),
        verdict("approve"),
        answers("Paris"),
    )
    accepted, record = run(chat)
    assert accepted
    assert [r["verdict"] for r in record["rounds"]] == ["revise", "approve"]
    assert "Say more in the explanation." in sent[2]["messages"][1]["content"]


@pytest.mark.parametrize(
    ("replies", "reason", "technical"),
    [
        ([reply(free()), verdict("reject", "Too easy.")], "critic rejected: Too easy.", False),
        # The blind solver answers something else: the question is not clear enough.
        (
            [reply(free()), verdict("approve"), answers("Lyon")],
            "blind solve: the expected answer is not among its answers",
            False,
        ),
        (
            [reply(single()), verdict("approve"), answers("Lyon")],
            "blind solve: picked other options",
            False,
        ),
        # Never approved within three drafts.
        (
            [reply(free()), verdict("revise", "x")] * 3,
            "not approved after 3 drafts",
            False,
        ),
        # Two broken replies: a technical failure, the start stays free for a later walk.
        (["not json", "still not json"], "writer failed", True),
        ([reply(free()), LLMError("timeout"), LLMError("timeout")], "critic failed", True),
    ],
)
def test_rejected_walks(replies: list[str | Exception], reason: str, technical: bool) -> None:
    chat, _ = canned(*replies)
    accepted, record = run(chat)
    assert not accepted
    assert record["reason"].startswith(reason)
    assert record["technical"] is technical


def test_a_broken_draft_is_written_again_with_the_reason() -> None:
    giveaway = free(question="Is Paris the capital of France?")
    chat, sent = canned(reply(giveaway), reply(free()), verdict("approve"), answers("Paris"))
    accepted, record = run(chat)
    assert accepted
    assert "the question contains its own answer" in sent[1]["messages"][1]["content"]
    # The record keeps the request that produced the accepted draft.
    assert "its own answer" in record["prompt"]


def test_an_answer_the_pool_has_too_often_goes_back_to_the_writer() -> None:
    index = PoolIndex()
    for number in range(2):
        index.add(
            {"start_entity": f"Q{number}", "mentioned": [], "question": free(question=f"Q{number}")}
        )
    other = free(question="Which country has Paris as its capital?", expected_answer="France")
    chat, sent = canned(reply(free()), reply(other), verdict("approve"), answers("France"))
    accepted, record = run(chat, index)
    assert accepted
    assert [r["verdict"] for r in record["rounds"]] == ["code", "approve"]
    assert "already the answer of 2 questions" in sent[1]["messages"][1]["content"]


def test_existing_questions_about_the_entities_are_shown() -> None:
    index = PoolIndex()
    index.add({"start_entity": "Q1", "mentioned": ["Q90"], "question": free()})
    chat, sent = canned(reply(single()), verdict("approve"), answers("Paris"))
    run(chat, index)
    assert "Which city is the capital of France? [Paris]" in sent[0]["messages"][1]["content"]


def test_usage_limit_stops_the_walk() -> None:
    chat, _ = canned(UsageLimitReached("monthly limit"))
    with pytest.raises(UsageLimitReached):
        run(chat)


def test_reply_in_a_code_fence_is_read() -> None:
    fenced = "Here it is:\n```json\n" + reply(free()) + "\n```"
    chat, _ = canned(fenced, verdict("approve"), answers("Paris"))
    assert run(chat)[0]


# --- The checks on the writer's reply ---


def choice(**changes: Any) -> dict[str, Any]:
    return single(**changes)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"question": "Which city?"}, "needs an expected_answer"),
        ({"question": "Short?"}, "does not match the schema"),
        (free(expected_answer=""), "needs an expected_answer"),
        (free(format="essay"), "does not match the schema"),
        (free(extra="field"), "does not match the schema"),
        (free(options=["Paris", "Lyon"]), "must not have options"),
        # Giveaways: the answer, or an accepted form of it, is part of the question.
        (free(question="Is Paris the capital of France, or is it Lyon?"), "its own answer"),
        (free(accepted_answers=["Capital of France"]), "its own answer"),
        (choice(options=["Paris"]), "needs 2 to 5 options"),
        (choice(options=["Paris", "paris ", "Lyon"]), "must be distinct"),
        (choice(options=["Paris", "", "Lyon"]), "1 to 80 characters"),
        (choice(correct_options=["Nice"]), "not among the options"),
        (choice(options=["Lyon", "Paris", "All of the above"]), "must not combine"),
        (choice(options=["Lyon", "Paris", "Keine der genannten"]), "must not combine"),
        (choice(correct_options=["Paris", "Lyon"]), "exactly one correct"),
        (choice(format="multiple", correct_options=["Paris"]), "at least two correct"),
        (
            choice(question="Which of these, like Paris, is the capital of France?"),
            "names only the correct option",
        ),
        (
            choice(format="order", options=["A1", "B2"], correct_options=["A1", "B2"]),
            "3 to 4 options",
        ),
        (
            choice(format="order", options=["A1", "B2", "C3"], correct_options=["A1", "B2"]),
            "every option once",
        ),
    ],
)
def test_broken_drafts(data: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        check_question(data)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (free(accepted_answers=[" Paname ", "paris", ""]), "Paris"),
        (choice(), "Paris"),
        (
            choice(format="multiple", options=["A1", "B2", "C3"], correct_options=["C3", "A1"]),
            "A1, C3",
        ),
        (
            choice(format="order", options=["A1", "B2", "C3"], correct_options=["C3", "A1", "B2"]),
            "C3, A1, B2",
        ),
        # True or false may use the word "true".
        (
            choice(
                question="True or false: Paris is in France.",
                options=["True", "False"],
                correct_options=["True"],
            ),
            "True",
        ),
    ],
)
def test_good_drafts(data: dict[str, Any], expected: str) -> None:
    assert check_question(data).expected_answer == expected


@pytest.mark.parametrize(
    ("text", "answers", "found"),
    [
        ("Where did the French Revolution take place?", ["France"], None),
        ("What was the language of the French Empire?", ["French"], "French"),
        ("Who founded the Mongol Empire?", ["Mongol  empire!"], "Mongol  empire!"),
        ("Which UN agency is based in Paris?", ["UN"], None),  # too short to check
    ],
)
def test_find_giveaway(text: str, answers: list[str], found: str | None) -> None:
    assert find_giveaway(text, answers) == found


def test_every_writer_example_is_a_valid_question() -> None:
    for example in EXAMPLES:
        assert check_question(example).explanation


@pytest.mark.parametrize(
    ("data", "solved", "miss"),
    [
        (free(accepted_answers=["Paname"]), ["paname"], None),
        (free(), ["Lyon", "Paris"], None),
        (free(), ["Lyon"], "the expected answer is not among its answers"),
        (single(), ["Paris"], None),
        (single(), ["Paris", "Lyon"], "picked other options"),
        (
            choice(format="order", options=["A1", "B2", "C3"], correct_options=["C3", "A1", "B2"]),
            ["C3", "B2", "A1"],
            "sorted differently",
        ),
    ],
)
def test_solver_miss(data: dict[str, Any], solved: list[str], miss: str | None) -> None:
    assert solver_miss(check_question(data), solved) == miss


def test_the_question_model_keeps_the_writers_notes() -> None:
    question = check_question({**free(), "candidates": ["a", "b"], "review": "Keep."})
    assert isinstance(question, Question)
    assert question.candidates == ["a", "b"]
