"""Pool and hybrid question sources through the HTTP API, and reading the pool files."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.models import Question
from app.game.matcher import MatcherJudge
from app.llm.generator import GeneratedQuestion
from app.pool.records import PoolQuestion, append_record, pool_path
from app.pool.store import PoolStore, to_entry
from tests.test_game_api import Game

NOW = datetime(2026, 11, 2, tzinfo=UTC)


def record(number: int, start_type: str = "city", **question: object) -> PoolQuestion:
    fields: dict[str, object] = {
        "question": f"Pool question {number}: where is Place {number}?",
        "expected_answer": "Secretland",
        "accepted_answers": ["Hiddenland"],
        "explanation": "Secretland it is.",
    }
    fields.update(question)
    return PoolQuestion(
        id=f"p{number:03d}",
        language="en",
        created_at=NOW,
        start_entity=f"P{number}",
        start_type=start_type,
        entities=[f"P{number}"],
        mentioned=[],
        facts=f"Facts {number}",
        question=GeneratedQuestion.model_validate(fields),
        solver_answers=["Secretland", "Geheimland"],
        graph_aliases=["Jupiter"],
        generator_model="pool-model",
        critic_model="critic",
        prompt=f"Prompt {number}",
        rounds=[],
        seconds=1,
        calls=3,
    )


def use_pool(game: Game, tmp_path: Path, mode: str, count: int) -> None:
    for number in range(1, count + 1):
        append_record(pool_path(tmp_path, "en"), record(number))
    game.pool = PoolStore(tmp_path)
    game.mode = mode  # type: ignore[assignment]
    if mode == "pool":
        game.judge_checker = MatcherJudge()


def stored(game: Game, run_id: str) -> list[Question]:
    with game.sessions() as session:
        rows = session.scalars(select(Question).order_by(Question.id))
        return [q for q in rows if str(q.run_id) == run_id]


def test_pool_mode_serves_unasked_questions_and_judges_by_code(game: Game, tmp_path: Path) -> None:
    use_pool(game, tmp_path, "pool", 3)
    game.life_rules = game.life_rules.__class__(combo=5, max_lives=3, start_lives=3)
    run_id = game.start()
    texts = []
    for answer in ["secretlnd", "Geheimland", "Jupiter"]:  # typo, solver form, graph alias
        texts.append(game.question(run_id).json()["text"])
        game.answer(run_id, answer)
    assert sorted(texts) == [f"Pool question {n}: where is Place {n}?" for n in (1, 2, 3)]
    rows = stored(game, run_id)
    assert [q.correct for q in rows] == [True, True, False]
    assert all(q.pool_question_id for q in rows)
    assert rows[0].generator_model == "pool-model"
    # No live question and no LLM judge call.
    assert game.generator.languages == []
    assert game.judge.calls == []


def test_pool_mode_repeats_the_least_recent_question_but_never_within_a_run(
    game: Game, tmp_path: Path
) -> None:
    use_pool(game, tmp_path, "pool", 2)
    first = game.start()
    game.question(first)
    game.answer(first, "Secretland")
    game.question(first)
    game.answer(first, "Secretland")
    asked_first = [q.pool_question_id for q in stored(game, first)]
    # The third question of the run: every pool question was asked in this run.
    assert game.question(first).status_code == 503

    second = game.start()
    assert game.question(second).status_code == 200
    # The one asked longest ago comes back first.
    assert stored(game, second)[0].pool_question_id == asked_first[0]


def test_hybrid_mode_goes_live_when_the_pool_is_used_up(game: Game, tmp_path: Path) -> None:
    use_pool(game, tmp_path, "hybrid", 1)
    run_id = game.start()
    assert game.question(run_id).json()["text"].startswith("Pool question 1")
    game.answer(run_id, "Secretland")
    assert game.question(run_id).json()["text"] == "In which country is Place 1?"
    assert game.generator.languages == ["en"]
    # The pool question was judged by the configured judge, with the solver's answers.
    item, _ = game.judge.calls[0]
    assert "Geheimland" in item.accepted_answers


def test_hybrid_mode_falls_back_to_the_pool_when_live_fails(game: Game, tmp_path: Path) -> None:
    use_pool(game, tmp_path, "hybrid", 1)
    first = game.start()
    game.question(first)
    game.answer(first, "Secretland")
    game.generator.fail = True
    second = game.start()
    assert game.question(second).json()["text"].startswith("Pool question 1")


def test_pool_mode_without_questions_in_the_language(game: Game, tmp_path: Path) -> None:
    use_pool(game, tmp_path, "pool", 1)
    run_id = game.client.post("/api/runs", json={"language": "de"}).json()["run_id"]
    response = game.question(run_id)
    assert response.status_code == 503
    assert response.json()["code"] == "no_questions_in_language"


def test_choice_options_are_shuffled_when_served(game: Game, tmp_path: Path) -> None:
    options = ["Alpha", "Beta", "Gamma", "Delta"]
    choice = record(
        1,
        format="single",
        question="Which of these is the first letter?",
        options=options,
        correct_options=["Alpha"],
        expected_answer="",
        accepted_answers=[],
    )
    append_record(pool_path(tmp_path, "en"), choice)
    game.pool = PoolStore(tmp_path)
    game.mode = "pool"
    run_id = game.start()
    shown = game.question(run_id).json()["options"]
    assert sorted(shown) == sorted(options)
    row = stored(game, run_id)[0]
    assert row.options is not None and row.correct_options is not None
    assert row.options[row.correct_options[0]] == "Alpha"


def test_store_skips_a_half_written_line_and_rereads_changes(tmp_path: Path) -> None:
    path = pool_path(tmp_path, "en")
    append_record(path, record(1))
    with path.open("a", encoding="utf-8") as file:
        file.write('{"id": "p002", "lang')
    store = PoolStore(tmp_path)
    assert [entry.id for entry in store.entries("en")] == ["p001"]
    path.write_text(record(1).model_dump_json() + "\n" + record(2).model_dump_json() + "\n")
    assert [entry.id for entry in store.entries("en")] == ["p001", "p002"]
    assert store.entries("de") == []


def test_entry_answers_combine_writer_and_solver_but_not_graph_aliases() -> None:
    entry = to_entry(record(1))
    assert entry.other_answers == ("Hiddenland", "Geheimland")


@pytest.mark.parametrize("mode", ["hybrid", "pool"])
def test_pool_modes_need_a_pool(mode: str) -> None:
    from app.game.service import GameService

    with pytest.raises(ValueError):
        GameService(None, None, None, MatcherJudge(), mode=mode)  # type: ignore[arg-type]
