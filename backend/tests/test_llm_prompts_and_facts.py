from pathlib import Path

import pytest

from app.graph.model import GraphEdge, GraphNode, QuestionSeed
from app.llm.facts import format_seed, format_year
from app.llm.prompts import load_prompt


def test_prompt_files_load_and_render() -> None:
    generator = load_prompt("generate_question")
    assert "trivia" in generator.system
    assert "FACTS HERE" in generator.render_user(facts="FACTS HERE")

    judge = load_prompt("judge_answer")
    user = judge.render_user(
        question="Q",
        expected_answer="A",
        accepted_answers="[]",
        numeric_range="none",
        player_answer="$question ${expected_answer}",
    )
    # Values are inserted verbatim: player text cannot pull in other placeholders.
    assert "<player_answer>\n$question ${expected_answer}\n</player_answer>" in user


def test_prompt_without_marker_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "broken.md").write_text("no marker here", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        load_prompt("broken", tmp_path)


@pytest.mark.parametrize(("year", "text"), [(1789, "1789"), (-44, "44 BC"), (0, "0")])
def test_format_year(year: int, text: str) -> None:
    assert format_year(year) == text


def test_format_seed() -> None:
    caesar = GraphNode(
        "Q1048",
        "Julius Caesar",
        "person",
        "Roman general and dictator",
        ("Caesar", "Cäsar"),
        {"birth_year": -100, "death_year": -44},
        fame="world famous",
    )
    rome = GraphNode("Q220", "Rome", "city", facts={"population": 2748109, "population_year": 2023})
    gaul = GraphNode("Q202311", "Gallic War", "war", facts={"start_year": -58})
    seed = QuestionSeed(
        start=caesar,
        nodes=(caesar, rome, gaul),
        edges=(
            GraphEdge("Q1048", "PLACE_OF_BIRTH", "Q220"),
            GraphEdge("Q1048", "PARTICIPATED_IN_CONFLICT", "Q202311", start_year=-58),
        ),
    )
    assert format_seed(seed) == "\n".join(
        [
            "Entities:",
            "- Julius Caesar (person, world famous; Roman general and dictator): "
            "born 100 BC; died 44 BC. "
            "Also known as: Caesar, Cäsar",
            "- Rome (city): population 2,748,109 (as of 2023)",
            "- Gallic War (war): start 58 BC",
            "",
            "Relations (walked in this order):",
            "- Julius Caesar -- place of birth --> Rome",
            "- Julius Caesar -- participated in conflict --> Gallic War (from 58 BC)",
        ]
    )
