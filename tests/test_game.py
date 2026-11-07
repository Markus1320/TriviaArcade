"""Whole runs through the HTTP API, with a tiny pool file and a temporary SQLite file.

TestClient sends requests to the app without a real server. The clock is replaced, so a
test can let time pass without waiting.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from game import runs
from game.main import create_app
from game.settings import Settings


def record(number: int, question: dict) -> dict:
    """A pool line as poolgen writes it, reduced to what the game reads."""
    return {
        "id": f"q{number}",
        "language": "en",
        "start_type": f"type{number}",
        "question": {"topic": "a topic", "explanation": f"Explanation {number}.", **question},
        "solver_answers": [],
        "generator_model": "writer-model",
        "prompt": "the writer's request",
    }


FREE = record(
    1,
    {
        "format": "free",
        "question": "Which river flows through Vienna?",
        "expected_answer": "Danube",
        "accepted_answers": ["Donau"],
    },
)
SINGLE = record(
    2,
    {
        "format": "single",
        "question": "Which country has more people?",
        "options": ["Nigeria", "Russia"],
        "correct_options": ["Nigeria"],
        "expected_answer": "Nigeria",
    },
)
MULTIPLE = record(
    3,
    {
        "format": "multiple",
        "question": "Which of these are planets?",
        "options": ["Mars", "Pluto", "Venus", "Ceres"],
        "correct_options": ["Mars", "Venus"],
        "expected_answer": "Mars, Venus",
    },
)
ORDER = record(
    4,
    {
        "format": "order",
        "question": "Sort these from oldest to newest.",
        "options": ["Rome", "Berlin", "Brasília"],
        "correct_options": ["Rome", "Berlin", "Brasília"],
        "expected_answer": "Rome, Berlin, Brasília",
    },
)
ALL = [FREE, SINGLE, MULTIPLE, ORDER]


class Clock:
    def __init__(self) -> None:
        self.time = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.time

    def advance(self, seconds: float) -> None:
        self.time += timedelta(seconds=seconds)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(runs, "now", clock)
    return clock


def game(tmp_path: Path, pool: list[dict], **settings: int) -> TestClient:
    lines = "".join(json.dumps(line) + "\n" for line in pool)
    (tmp_path / "en.jsonl").write_text(lines, encoding="utf-8")
    config = Settings(database=str(tmp_path / "game.db"), pool_dir=str(tmp_path), **settings)
    return TestClient(create_app(config))


def right_answer(question: dict) -> dict:
    """The body of a correct answer to a question as the browser got it."""
    record = next(r["question"] for r in ALL if r["question"]["question"] == question["text"])
    if record["format"] == "free":
        return {"answer": record["expected_answer"]}
    picked = [question["options"].index(option) for option in record["correct_options"]]
    # Order questions in the correct order, the others as the server sends them: ascending.
    return {"selected": picked if record["format"] == "order" else sorted(picked)}


def wrong_answer(question: dict) -> dict:
    if question["format"] == "free":
        return {"answer": "Thames"}
    if question["format"] == "order":
        # Every option, but not in the correct order.
        right = right_answer(question)["selected"]
        return {"selected": [right[1], right[0], *right[2:]]}
    # The wrong options of a choice question.
    right = right_answer(question)["selected"]
    return {"selected": [i for i in range(len(question["options"])) if i not in right]}


def new_question(client: TestClient, run_id: str) -> dict:
    question = client.post(f"/api/runs/{run_id}/question").json()
    client.post(f"/api/runs/{run_id}/question/start")
    return question


def test_correct_answers_in_every_format_and_a_1up(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, ALL, start_lives=0)
    run_id = client.post("/api/runs", json={"language": "en"}).json()["run_id"]
    formats = set()
    for number in range(1, 5):
        question = new_question(client, run_id)
        formats.add(question["format"])
        assert question["number"] == number
        # The browser never gets the answer with the question.
        assert "Danube" not in json.dumps(question)
        verdict = client.post(f"/api/runs/{run_id}/answer", json=right_answer(question)).json()
        assert verdict["correct"] is True
        assert verdict["streak"] == number
        assert verdict["expected_answer"] is None
        assert verdict["explanation"].startswith("Explanation")
        # The third correct answer in a row earns a 1UP.
        assert verdict["life_earned"] is (number == 3)
    assert formats == {"free", "single", "multiple", "order"}
    assert verdict["lives"] == 1
    assert verdict["combo"] == 1


def test_typed_answer_with_typo_or_another_form(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, [FREE, {**FREE, "id": "q1b"}])
    run_id = client.post("/api/runs").json()["run_id"]
    for typed in ["danub", "Donau"]:
        new_question(client, run_id)
        verdict = client.post(f"/api/runs/{run_id}/answer", json={"answer": typed}).json()
        assert verdict["correct"] is True, typed


def test_wrong_answer_saved_by_a_1up_then_game_over(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, [SINGLE, MULTIPLE], start_lives=1)
    run_id = client.post("/api/runs").json()["run_id"]

    question = new_question(client, run_id)
    verdict = client.post(f"/api/runs/{run_id}/answer", json=wrong_answer(question)).json()
    assert verdict["correct"] is False
    assert verdict["saved"] is True
    assert verdict["game_over"] is False
    assert verdict["lives"] == 0
    assert verdict["correct_options"] == right_answer(question)["selected"]

    question = new_question(client, run_id)
    verdict = client.post(f"/api/runs/{run_id}/answer", json=wrong_answer(question)).json()
    assert verdict["game_over"] is True
    assert verdict["saved"] is False

    # After a reload the game over screen gets the last question's answer.
    state = client.get(f"/api/runs/{run_id}").json()
    assert state["over"] is True
    assert state["last_format"] == question["format"]
    assert state["last_options"] == question["options"]
    assert state["last_selected_options"] == wrong_answer(question)["selected"]
    assert state["last_explanation"].startswith("Explanation")
    response = client.post(f"/api/runs/{run_id}/question")
    assert response.status_code == 409
    assert response.json()["code"] == "run_over"


def test_skip_with_a_1up(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, ALL, start_lives=1)
    run_id = client.post("/api/runs").json()["run_id"]
    new_question(client, run_id)
    verdict = client.post(f"/api/runs/{run_id}/skip").json()
    assert verdict["skipped"] is True
    assert verdict["lives"] == 0
    assert verdict["streak"] == 0
    assert verdict["game_over"] is False

    new_question(client, run_id)
    response = client.post(f"/api/runs/{run_id}/skip")
    assert response.status_code == 409
    assert response.json()["code"] == "no_life_left"


def test_time_limit(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, ALL, start_lives=1)
    run_id = client.post("/api/runs").json()["run_id"]

    # Showing the question again after a reload keeps the clock running.
    question = new_question(client, run_id)
    clock.advance(10)
    again = client.post(f"/api/runs/{run_id}/question").json()
    assert again["question_id"] == question["question_id"]
    assert client.post(f"/api/runs/{run_id}/question/start").json()["seconds_left"] == 20

    # A right answer that arrives too late counts as wrong.
    clock.advance(25)
    verdict = client.post(f"/api/runs/{run_id}/answer", json=right_answer(question)).json()
    assert verdict["correct"] is False
    assert verdict["timed_out"] is True
    assert verdict["saved"] is True

    # The countdown ran out with nothing typed and no 1UP left: game over.
    new_question(client, run_id)
    verdict = client.post(f"/api/runs/{run_id}/timeout").json()
    assert verdict["timed_out"] is True
    assert verdict["game_over"] is True


def test_invalid_answers_keep_the_question_open(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, [SINGLE])
    run_id = client.post("/api/runs").json()["run_id"]
    question = new_question(client, run_id)
    for body in [{"answer": "Nigeria"}, {"selected": [0, 1]}, {"selected": [5]}, {}]:
        response = client.post(f"/api/runs/{run_id}/answer", json=body)
        assert response.status_code == 422, body
    assert client.get(f"/api/runs/{run_id}").json()["open_question"] == question | {
        "seconds_left": 30.0
    }


def test_claim_and_leaderboard(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, ALL, start_lives=0)

    def play(correct_answers: int) -> str:
        run_id = client.post("/api/runs").json()["run_id"]
        for _ in range(correct_answers):
            question = new_question(client, run_id)
            client.post(f"/api/runs/{run_id}/answer", json=right_answer(question))
        client.post(f"/api/runs/{run_id}/question")
        client.post(f"/api/runs/{run_id}/timeout")
        clock.advance(60)
        return run_id

    first = play(1)
    assert client.post(f"/api/runs/{first}/claim", json={"handle": "x"}).status_code == 422
    claimed = client.post(f"/api/runs/{first}/claim", json={"handle": "ace"}).json()
    assert claimed == {"handle": "ACE", "streak": 1, "rank": 1, "personal_best": True}
    again = client.post(f"/api/runs/{first}/claim", json={"handle": "ACE"})
    assert again.json()["code"] == "run_already_claimed"

    claimed = client.post(f"/api/runs/{play(2)}/claim", json={"handle": "BOB"}).json()
    assert claimed["rank"] == 1
    # A worse run of ACE is stored but does not change the leaderboard.
    claimed = client.post(f"/api/runs/{play(0)}/claim", json={"handle": "ACE"}).json()
    assert claimed == {"handle": "ACE", "streak": 0, "rank": 2, "personal_best": False}

    board = client.get("/api/leaderboard").json()
    assert [(row["rank"], row["handle"], row["streak"]) for row in board] == [
        (1, "BOB", 2),
        (2, "ACE", 1),
    ]
    assert client.get("/api/players").json() == ["ACE", "BOB"]

    active = client.post("/api/runs").json()["run_id"]
    response = client.post(f"/api/runs/{active}/claim", json={"handle": "ACE"})
    assert response.json()["code"] == "run_not_over"


def test_question_log_shows_finished_runs_without_answers(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, [FREE, SINGLE], start_lives=0)
    run_id = client.post("/api/runs").json()["run_id"]
    question = new_question(client, run_id)
    client.post(f"/api/runs/{run_id}/answer", json=right_answer(question))
    assert client.get("/api/question-log").json()["questions"] == []  # the run is still on

    question = new_question(client, run_id)
    client.post(f"/api/runs/{run_id}/answer", json=wrong_answer(question))
    log = client.get("/api/question-log").json()
    assert [entry["number"] for entry in log["questions"]] == [2, 1]
    assert [entry["correct"] for entry in log["questions"]] == [False, True]
    assert log["questions"][0]["notes"]["topic"] == "a topic"
    assert log["has_more"] is False
    assert "Thames" not in json.dumps(log)


def test_every_question_once_then_the_least_recent(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, ALL, start_lives=3)
    asked = []
    for _ in range(2):
        run_id = client.post("/api/runs").json()["run_id"]
        for _ in range(2):
            asked.append(new_question(client, run_id)["text"])
            client.post(f"/api/runs/{run_id}/skip")
    # Four questions in the pool, four asked: no question twice.
    assert len(set(asked)) == 4


def test_language_without_questions(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, ALL)
    run_id = client.post("/api/runs", json={"language": "de"}).json()["run_id"]
    response = client.post(f"/api/runs/{run_id}/question")
    assert response.status_code == 503
    assert response.json()["code"] == "no_questions_in_language"


def test_unknown_run(tmp_path: Path, clock: Clock) -> None:
    client = game(tmp_path, ALL)
    response = client.get("/api/runs/nope")
    assert response.status_code == 404
    assert response.json()["code"] == "run_not_found"
