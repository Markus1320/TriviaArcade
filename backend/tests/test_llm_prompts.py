import random

from app.llm.generator import parse_generated_question
from app.llm.generator_prompt import (
    CHOICE_EXAMPLES,
    CLAIM_HINTS,
    EXAMPLES,
    FALSE_CLAIM_HINT,
    FALSE_CLAIM_SHARE,
    FREE_EXAMPLES,
    MULTIPLE_EXAMPLES,
    MULTIPLE_SHARE,
    TRUE_CLAIM_HINT,
    format_example,
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


def _blocks(seeds: range, language: str = "en") -> list[str]:
    return [pick_examples(random.Random(seed), language) for seed in seeds]


def test_pick_examples_usually_returns_one_of_each_group() -> None:
    free = [format_example(example) for example in FREE_EXAMPLES]
    choice = [format_example(example) for example in CHOICE_EXAMPLES]
    first_is_free = set()
    mixed = [block for block in _blocks(range(40)) if block.startswith("Two examples")]
    assert mixed
    for block in mixed:
        _intro, first, second = block.split("\n\n")
        assert "Suggested question type" not in block
        assert sum(example in free for example in (first, second)) == 1
        assert sum(example in choice for example in (first, second)) == 1
        first_is_free.add(first in free)
    # The order varies, so the model does not learn to prefer one format.
    assert first_is_free == {True, False}


def test_pick_examples_sometimes_suggests_multiple_choice() -> None:
    multiple = [format_example(example) for example in MULTIPLE_EXAMPLES]
    assert len(multiple) >= 3
    blocks = _blocks(range(2000))
    suggested = [block for block in blocks if block.startswith("One example")]
    assert abs(len(suggested) / len(blocks) - MULTIPLE_SHARE) < 0.03
    for block in suggested:
        _intro, example, suggestion = block.split("\n\n")
        assert example in multiple
        assert 'Suggested question type for this request: a "multiple" question' in suggestion


def test_example_block_follows_the_language() -> None:
    blocks = _blocks(range(40), "de")
    assert {block.split(" ")[0] for block in blocks} == {"Zwei", "Ein"}
    assert all("auf Deutsch" in block for block in blocks)
    assert any("Vorgeschlagener Fragetyp" in block for block in blocks)


def test_example_groups_are_balanced() -> None:
    assert len(FREE_EXAMPLES) == len(CHOICE_EXAMPLES)
    assert all(example["format"] == "free" for example in FREE_EXAMPLES)
    formats = [example["format"] for example in CHOICE_EXAMPLES]
    assert set(formats) == {"single", "multiple"}


def test_true_false_hint_prefers_false_claims() -> None:
    rng = random.Random(42)
    hints = [pick_true_false_hint(rng) for _ in range(1000)]
    assert set(hints) == {FALSE_CLAIM_HINT, TRUE_CLAIM_HINT}
    false_share = hints.count(FALSE_CLAIM_HINT) / len(hints)
    assert abs(false_share - FALSE_CLAIM_SHARE) < 0.05


def test_examples_are_valid_generator_output() -> None:
    for example in EXAMPLES:
        # Every example is valid output, with a real, short explanation.
        question = parse_generated_question(format_example(example))
        assert 20 < len(question.explanation) <= 200


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


def test_generator_request_exists_in_german() -> None:
    values = {"facts": "FACTS HERE", "examples": "EXAMPLES HERE", "true_false_hint": "HINT"}
    german = GENERATOR_PROMPT.render_user("de", **values)
    assert "auf Deutsch" in german
    assert "FACTS HERE" in german
    assert "EXAMPLES HERE" in german
    assert "in English" in GENERATOR_PROMPT.render_user("en", **values)
    # Unknown languages fall back to English instead of failing.
    assert GENERATOR_PROMPT.render_user("xx", **values) == GENERATOR_PROMPT.render_user(**values)
    # The system prompt stays English and explains the mismatch.
    assert "language of the game" in GENERATOR_PROMPT.system


def test_true_false_hint_follows_the_language() -> None:
    hints = {pick_true_false_hint(random.Random(seed), language="de") for seed in range(50)}
    assert hints == set(CLAIM_HINTS["de"])
