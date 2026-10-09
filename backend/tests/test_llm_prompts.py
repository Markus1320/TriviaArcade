import random

from app.llm.generator import parse_generated_question
from app.llm.generator_prompt import (
    EXAMPLES,
    EXAMPLES_PER_QUESTION,
    FALSE_CLAIM_HINT,
    FALSE_CLAIM_SHARE,
    TRUE_CLAIM_HINT,
    pick_examples,
    pick_true_false_hint,
)
from app.llm.generator_prompt import PROMPT as GENERATOR_PROMPT
from app.llm.judge_prompt import PROMPT as JUDGE_PROMPT


def test_generator_prompt_renders_facts_and_examples() -> None:
    user = GENERATOR_PROMPT.render_user(
        facts="FACTS HERE", examples="EXAMPLES HERE", true_false_hint="HINT HERE"
    )
    assert "FACTS HERE" in user
    assert "EXAMPLES HERE" in user
    assert "HINT HERE" in user
    assert "trivia" in GENERATOR_PROMPT.system


def test_pick_examples_returns_distinct_examples() -> None:
    picked = pick_examples().split("\n\n")
    assert len(picked) == EXAMPLES_PER_QUESTION
    assert len(set(picked)) == EXAMPLES_PER_QUESTION
    assert all(example in EXAMPLES for example in picked)


def test_true_false_hint_prefers_false_claims() -> None:
    rng = random.Random(42)
    hints = [pick_true_false_hint(rng) for _ in range(1000)]
    assert set(hints) == {FALSE_CLAIM_HINT, TRUE_CLAIM_HINT}
    false_share = hints.count(FALSE_CLAIM_HINT) / len(hints)
    assert abs(false_share - FALSE_CLAIM_SHARE) < 0.05


def test_examples_are_valid_generator_output() -> None:
    for example in EXAMPLES:
        parse_generated_question(example)


def test_judge_prompt_inserts_player_answer_verbatim() -> None:
    user = JUDGE_PROMPT.render_user(
        question="Q",
        expected_answer="A",
        accepted_answers="[]",
        player_answer="$question ${expected_answer}",
    )
    # Values are inserted verbatim: player text cannot pull in other placeholders.
    assert "<player_answer>\n$question ${expected_answer}\n</player_answer>" in user
    assert "untrusted" in JUDGE_PROMPT.system
