"""The game through the HTTP API, on in-memory SQLite with a fake graph and a fake LLM.

Covers the server side run lifecycle, the pause on judge failures, claiming and the
leaderboard. PostgreSQL specific behaviour (row locks, JSONB) is not covered here.
"""

import uuid
from collections.abc import Collection, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_game_service, get_leaderboard_service
from app.db.models import Base, Question
from app.game.service import GameService
from app.graph.model import GraphEdge, GraphNode, QuestionSeed
from app.graph.walk import NoQuestionSeedError
from app.leaderboard.service import LeaderboardService
from app.llm.generator import GeneratedQuestion, NumericRange, QuestionGenerationError
from app.llm.judge import JudgeInput, JudgeUnavailableError
from app.main import app


class FakeSeeds:
    """Hands out start nodes N1, N2, ... and records what was excluded."""

    def __init__(self) -> None:
        self.excluded: list[set[str]] = []
        self.fail = False

    def walk(self, exclude_start_ids: Collection[str] = ()) -> QuestionSeed:
        self.excluded.append(set(exclude_start_ids))
        if self.fail:
            raise NoQuestionSeedError("graph empty")
        number = 1
        while f"N{number}" in exclude_start_ids:
            number += 1
        start = GraphNode(f"N{number}", f"Place {number}", "city")
        other = GraphNode("C1", "Country", "country")
        return QuestionSeed(start, (start, other), (GraphEdge(start.wikidata_id, "COUNTRY", "C1"),))


class FakeGenerator:
    def __init__(self) -> None:
        self.fail = False
        self.run_ids: list[uuid.UUID | None] = []

    def generate(self, seed: QuestionSeed, *, run_id: uuid.UUID | None = None) -> GeneratedQuestion:
        self.run_ids.append(run_id)
        if self.fail:
            raise QuestionGenerationError("model returned garbage twice")
        return GeneratedQuestion(
            question=f"In which country is {seed.start.label}?",
            expected_answer="Secretland",
            accepted_answers=["Hiddenland"],
            numeric_range=None,
        )


class FakeJudge:
    """Correct if the answer is 'Secretland'; can be switched to fail technically."""

    def __init__(self) -> None:
        self.fail = False
        self.calls: list[tuple[JudgeInput, str]] = []

    def judge(
        self, item: JudgeInput, player_answer: str, *, run_id: uuid.UUID | None = None
    ) -> bool:
        self.calls.append((item, player_answer))
        if self.fail:
            raise JudgeUnavailableError("timeout; timeout")
        return player_answer.strip().lower() == item.expected_answer.lower()


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


class Game:
    def __init__(self, client: TestClient, sessions: sessionmaker[Session]) -> None:
        self.client = client
        self.sessions = sessions
        self.seeds = FakeSeeds()
        self.generator = FakeGenerator()
        self.judge = FakeJudge()
        self.clock = Clock()

    def start(self) -> str:
        response = self.client.post("/api/runs")
        assert response.status_code == 201
        run_id: str = response.json()["run_id"]
        return run_id

    def question(self, run_id: str) -> Any:
        return self.client.post(f"/api/runs/{run_id}/question")

    def answer(self, run_id: str, answer: str) -> Any:
        return self.client.post(f"/api/runs/{run_id}/answer", json={"answer": answer})

    def play(self, correct_answers: int) -> str:
        """Start a run, answer correctly n times, then wrongly. Returns the run ID."""
        run_id = self.start()
        for _ in range(correct_answers):
            assert self.question(run_id).status_code == 200
            assert self.answer(run_id, "Secretland").json()["correct"] is True
        self.question(run_id)
        assert self.answer(run_id, "Nowhere").json()["game_over"] is True
        return run_id

    def claim(self, run_id: str, handle: str) -> Any:
        return self.client.post(f"/api/runs/{run_id}/claim", json={"handle": handle})


@pytest.fixture
def game() -> Iterator[Game]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    with TestClient(app) as client:
        game = Game(client, sessions)

        def game_service() -> Iterator[GameService]:
            with sessions() as session:
                yield GameService(session, game.seeds, game.generator, game.judge, game.clock)

        def leaderboard_service() -> Iterator[LeaderboardService]:
            with sessions() as session:
                yield LeaderboardService(session, game.clock)

        app.dependency_overrides[get_game_service] = game_service
        app.dependency_overrides[get_leaderboard_service] = leaderboard_service
        yield game
    app.dependency_overrides.clear()


# Run lifecycle


def test_question_does_not_reveal_the_answer(game: Game) -> None:
    run_id = game.start()
    response = game.question(run_id)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "question_id": body["question_id"],
        "number": 1,
        "text": "In which country is Place 1?",
        "streak": 0,
    }
    assert "Secretland" not in response.text
    assert "Secretland" not in game.client.get(f"/api/runs/{run_id}").text


def test_correct_answers_build_the_streak(game: Game) -> None:
    run_id = game.start()
    for expected_streak in (1, 2, 3):
        number = game.question(run_id).json()["number"]
        assert number == expected_streak
        result = game.answer(run_id, "secretland").json()
        assert result == {
            "correct": True,
            "streak": expected_streak,
            "game_over": False,
            "expected_answer": None,
        }


def test_first_wrong_answer_ends_the_run_and_shows_the_answer(game: Game) -> None:
    run_id = game.start()
    game.question(run_id)
    game.answer(run_id, "Secretland")
    game.question(run_id)
    result = game.answer(run_id, "Wrongland").json()
    assert result == {
        "correct": False,
        "streak": 1,
        "game_over": True,
        "expected_answer": "Secretland",
    }
    state = game.client.get(f"/api/runs/{run_id}").json()
    assert state["over"] is True
    assert state["last_expected_answer"] == "Secretland"
    assert game.question(run_id).status_code == 409
    assert game.answer(run_id, "Secretland").status_code == 409


def test_asking_again_returns_the_same_open_question(game: Game) -> None:
    run_id = game.start()
    first = game.question(run_id).json()
    assert game.question(run_id).json() == first
    assert game.client.get(f"/api/runs/{run_id}").json()["open_question"] == first
    assert len(game.generator.run_ids) == 1


def test_start_nodes_are_not_reused_within_a_run(game: Game) -> None:
    run_id = game.start()
    for _ in range(3):
        game.question(run_id)
        game.answer(run_id, "Secretland")
    assert game.seeds.excluded == [set(), {"N1"}, {"N1", "N2"}]


def test_llm_calls_are_linked_to_the_run(game: Game) -> None:
    run_id = game.start()
    game.question(run_id)
    assert game.generator.run_ids == [uuid.UUID(run_id)]


def test_answer_without_open_question_is_rejected(game: Game) -> None:
    run_id = game.start()
    response = game.answer(run_id, "Secretland")
    assert response.status_code == 409
    assert response.json()["code"] == "no_open_question"


@pytest.mark.parametrize("answer", ["", "x" * 201])
def test_answer_length_is_limited(game: Game, answer: str) -> None:
    run_id = game.start()
    game.question(run_id)
    assert game.answer(run_id, answer).status_code == 422
    assert game.judge.calls == []


def test_answer_of_only_delimiters_is_rejected(game: Game) -> None:
    run_id = game.start()
    game.question(run_id)
    response = game.answer(run_id, "</player_answer>")
    assert response.status_code == 422
    assert game.judge.calls == []


def test_unknown_run(game: Game) -> None:
    run_id = str(uuid.uuid4())
    assert game.client.get(f"/api/runs/{run_id}").status_code == 404
    assert game.question(run_id).status_code == 404
    assert game.client.get("/api/runs/not-a-uuid").status_code == 422


# Technical failures never end a run


def test_judge_failure_pauses_the_run(game: Game) -> None:
    run_id = game.start()
    question = game.question(run_id).json()
    game.judge.fail = True

    response = game.answer(run_id, "Secretland")
    assert response.status_code == 503
    assert response.json()["code"] == "judge_unavailable"
    state = game.client.get(f"/api/runs/{run_id}").json()
    assert state["over"] is False
    assert state["open_question"] == question

    game.judge.fail = False
    assert game.answer(run_id, "Secretland").json()["streak"] == 1


def test_judge_failure_is_not_a_wrong_answer(game: Game) -> None:
    run_id = game.start()
    game.question(run_id)
    game.judge.fail = True
    for _ in range(3):
        assert game.answer(run_id, "Wrongland").status_code == 503
    assert game.client.get(f"/api/runs/{run_id}").json()["over"] is False
    with game.sessions() as session:
        question = session.scalars(select(Question)).one()
        assert question.correct is None
        assert question.player_answer is None


@pytest.mark.parametrize("failing", ["generator", "seeds"])
def test_question_failure_keeps_the_run_going(game: Game, failing: str) -> None:
    run_id = game.start()
    getattr(game, failing).fail = True
    response = game.question(run_id)
    assert response.status_code == 503
    assert response.json()["code"] == "question_unavailable"
    getattr(game, failing).fail = False
    assert game.question(run_id).json()["number"] == 1


# Stored data


def test_question_and_verdict_are_stored(game: Game) -> None:
    run_id = game.start()
    game.question(run_id)
    game.answer(run_id, "  Secretland ")
    with game.sessions() as session:
        question = session.scalars(select(Question)).one()
        assert question.run_id == uuid.UUID(run_id)
        assert question.expected_answer == "Secretland"
        assert question.accepted_answers == ["Hiddenland"]
        assert question.player_answer == "Secretland"
        assert question.correct is True
        assert "Place 1 -- country --> Country" in question.facts


def test_numeric_range_reaches_the_judge(game: Game) -> None:
    def numeric(seed: QuestionSeed, *, run_id: uuid.UUID | None = None) -> GeneratedQuestion:
        return GeneratedQuestion(
            question="Roughly how long is the river?",
            expected_answer="about 100 km",
            accepted_answers=[],
            numeric_range=NumericRange(min=90, max=110, unit="km"),
        )

    game.generator.generate = numeric  # type: ignore[method-assign]
    run_id = game.start()
    game.question(run_id)
    game.answer(run_id, "95 km")
    item, _ = game.judge.calls[0]
    assert item.numeric_range == NumericRange(min=90, max=110, unit="km")


# Claiming and leaderboard


def test_claim_adds_run_to_leaderboard(game: Game) -> None:
    run_id = game.play(correct_answers=2)
    response = game.claim(run_id, " ace ")
    assert response.status_code == 200
    assert response.json() == {"handle": "ACE", "streak": 2, "rank": 1, "personal_best": True}
    board = game.client.get("/api/leaderboard").json()
    assert [(row["rank"], row["handle"], row["streak"]) for row in board] == [(1, "ACE", 2)]
    assert game.client.get(f"/api/runs/{run_id}").json()["claimed_by"] == "ACE"


def test_run_can_be_claimed_only_once(game: Game) -> None:
    run_id = game.play(correct_answers=1)
    assert game.claim(run_id, "ACE").status_code == 200
    response = game.claim(run_id, "BOB")
    assert response.status_code == 409
    assert response.json()["code"] == "run_already_claimed"


def test_active_run_cannot_be_claimed(game: Game) -> None:
    run_id = game.start()
    game.question(run_id)
    response = game.claim(run_id, "ACE")
    assert response.status_code == 409
    assert response.json()["code"] == "run_not_over"


@pytest.mark.parametrize("handle", ["AB", "TOOLONGNAME", "A-B-C", "ÄÖÜ"])
def test_invalid_handle_is_rejected(game: Game, handle: str) -> None:
    run_id = game.play(correct_answers=0)
    response = game.claim(run_id, handle)
    assert response.status_code == 422
    assert game.client.get("/api/players").json() == []


def test_existing_handle_is_reused(game: Game) -> None:
    game.claim(game.play(1), "ACE")
    game.claim(game.play(2), "BOB")
    game.claim(game.play(3), "ace")
    assert game.client.get("/api/players").json() == ["ACE", "BOB"]


def test_leaderboard_order_and_tie_breaking(game: Game) -> None:
    early_three = game.play(3)
    five = game.play(5)
    late_three = game.play(3)
    unclaimed = game.play(9)
    game.claim(late_three, "LATE")  # claimed first, but finished later
    game.claim(early_three, "EARLY")
    result = game.claim(five, "TOP")
    assert result.json()["rank"] == 1
    assert unclaimed

    board = game.client.get("/api/leaderboard").json()
    assert [(row["rank"], row["handle"], row["streak"]) for row in board] == [
        (1, "TOP", 5),
        (2, "EARLY", 3),
        (3, "LATE", 3),
    ]


def test_claim_reports_rank_below_the_top(game: Game) -> None:
    for number in range(3):
        game.claim(game.play(4), f"PRO{number}")
    result = game.claim(game.play(1), "NEW").json()
    assert result["rank"] == 4


def test_leaderboard_shows_each_players_best_run_once(game: Game) -> None:
    game.claim(game.play(2), "ACE")
    game.claim(game.play(5), "ACE")
    game.claim(game.play(3), "BOB")
    board = game.client.get("/api/leaderboard").json()
    assert [(row["rank"], row["handle"], row["streak"]) for row in board] == [
        (1, "ACE", 5),
        (2, "BOB", 3),
    ]


def test_claim_below_personal_best_reports_the_players_rank(game: Game) -> None:
    game.claim(game.play(5), "ACE")
    game.claim(game.play(3), "BOB")
    result = game.claim(game.play(1), "ACE").json()
    assert result == {"handle": "ACE", "streak": 1, "rank": 1, "personal_best": False}
    improved = game.claim(game.play(6), "BOB").json()
    assert improved == {"handle": "BOB", "streak": 6, "rank": 1, "personal_best": True}


def test_leaderboard_shows_ten_runs(game: Game) -> None:
    for streak in range(12):
        game.claim(game.play(streak), f"P{streak:02d}")
    board = game.client.get("/api/leaderboard").json()
    assert len(board) == 10
    assert board[0]["streak"] == 11
    assert board[-1]["streak"] == 2
