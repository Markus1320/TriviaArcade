"""What a question is, and the checks on what the writer wrote.

A question is a JSON object in one of four formats:
- free: the player types; expected_answer and accepted_answers say what counts.
- single, multiple: the player picks from options; correct_options are the right ones.
  expected_answer is filled in by code (the correct options, joined).
- order: the player taps every option in order; correct_options is the correct order.

Before the question the writer fills in four note fields (topic, candidates, choice,
review) to work it out step by step. They are kept in the pool record, never shown to the
player.

check_question raises ValueError with a reason when the writer broke a rule; poolgen then
asks the writer again and tells it the reason.
"""

import random
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

# The note fields, in the order the writer fills them in.
NOTE_FIELDS = ("topic", "candidates", "choice", "review")
NOTE_LENGTH = 1500
# Options per format: (fewest, most). A single choice needs at least one wrong option; a
# multiple choice at least two correct and one wrong one.
OPTION_LIMITS = {"single": (2, 5), "multiple": (3, 6), "order": (3, 4)}
MAX_OPTION_LENGTH = 80
MAX_EXPECTED_ANSWER_LENGTH = 200
# Answers shorter than this are not checked by the giveaway check ("UN", "No", "5").
MIN_GIVEAWAY_LENGTH = 3
# Options that refer to the other options instead of being an answer themselves (English
# and German). They break shuffling and the "exactly these options" rule.
COMBINED_OPTIONS = (
    "all of the above", "none of the above", "all of them", "all of these",
    "none of them", "none of these", "both ", "neither ",
    "alle genannten", "alle oben", "alle drei", "keine der", "keines der", "keiner der",
    "beide", "sowohl ", "weder ",
)  # fmt: skip
# Option pairs kept in this order instead of being shuffled.
FIXED_ORDERS = (
    ("true", "false"),
    ("yes", "no"),
    ("wahr", "falsch"),
    ("richtig", "falsch"),
    ("ja", "nein"),
)

# The shape Ollama is asked to keep to (structured output). Written out instead of
# generated from the model, so it has no $ref indirections, which providers handle
# unevenly.
QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "candidates": {"type": "array", "items": {"type": "string"}},
        "choice": {"type": "string"},
        "review": {"type": "string"},
        "format": {"type": "string", "enum": ["free", "single", "multiple", "order"]},
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "correct_options": {"type": "array", "items": {"type": "string"}},
        "expected_answer": {"type": "string"},
        "accepted_answers": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": [*NOTE_FIELDS, "format", "question", "explanation"],
}


class Question(BaseModel):
    """Pydantic checks the types and lengths of the fields; check_question the rest."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(default="", max_length=NOTE_LENGTH)
    candidates: list[str] = Field(default_factory=list, max_length=6)
    choice: str = Field(default="", max_length=NOTE_LENGTH)
    review: str = Field(default="", max_length=NOTE_LENGTH)
    format: Literal["free", "single", "multiple", "order"] = "free"
    question: str = Field(min_length=10, max_length=300)
    options: list[str] = Field(default_factory=list, max_length=10)
    correct_options: list[str] = Field(default_factory=list, max_length=10)
    expected_answer: str = Field(default="", max_length=MAX_EXPECTED_ANSWER_LENGTH)
    accepted_answers: list[str] = Field(default_factory=list, max_length=20)
    # Shown to the player after answering. Optional: a missing explanation is not worth
    # rejecting an otherwise good question.
    explanation: str = Field(default="", max_length=400)

    @property
    def is_choice(self) -> bool:
        return self.format != "free"


def check_question(data: dict[str, Any]) -> Question:
    """The writer's reply as a checked Question. Raises ValueError with the reason."""
    try:
        question = Question.model_validate(data)
    except ValidationError as error:
        raise ValueError(f"output does not match the schema: {error}") from error
    question = question.model_copy(
        update={"question": question.question.strip(), "explanation": question.explanation.strip()}
    )
    return check_choice(question) if question.is_choice else check_free(question)


def check_free(question: Question) -> Question:
    if question.options or question.correct_options:
        raise ValueError("a free question must not have options")
    expected = question.expected_answer.strip()
    if not expected:
        raise ValueError("a free question needs an expected_answer")
    # Accepted answers: trimmed, no empties, no duplicates of the expected one.
    seen = {expected.casefold()}
    accepted = []
    for answer in question.accepted_answers:
        text = answer.strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            accepted.append(text)
    given_away = find_giveaway(question.question, [expected, *accepted])
    if given_away is not None:
        raise ValueError(f"the question contains its own answer: {given_away!r}")
    return question.model_copy(update={"expected_answer": expected, "accepted_answers": accepted})


def check_choice(question: Question) -> Question:
    options = [option.strip() for option in question.options]
    if any(not option or len(option) > MAX_OPTION_LENGTH for option in options):
        raise ValueError(f"options must have 1 to {MAX_OPTION_LENGTH} characters")
    combined = [option for option in options if option.casefold().startswith(COMBINED_OPTIONS)]
    if combined:
        raise ValueError(f"an option must not combine or exclude the others: {combined[0]!r}")
    by_key = {option.casefold(): option for option in options}
    if len(by_key) != len(options):
        raise ValueError("options must be distinct")
    low, high = OPTION_LIMITS[question.format]
    if not low <= len(options) <= high:
        raise ValueError(f"a {question.format} choice question needs {low} to {high} options")
    correct_keys = [option.strip().casefold() for option in question.correct_options]
    unknown = set(correct_keys) - set(by_key)
    if unknown:
        raise ValueError(f"correct_options are not among the options: {sorted(unknown)}")

    if question.format == "order":
        if len(correct_keys) != len(options) or len(set(correct_keys)) != len(correct_keys):
            raise ValueError("an order question lists every option once in correct_options")
        correct = [by_key[key] for key in correct_keys]
    else:
        correct = [option for option in options if option.casefold() in correct_keys]
        if question.format == "single" and len(correct) != 1:
            raise ValueError("a single choice question needs exactly one correct option")
        if question.format == "multiple" and not 2 <= len(correct) < len(options):
            raise ValueError(
                "a multiple choice question needs at least two correct and one wrong option"
            )
        # A question may name its options ("Which is longer, the Danube or the Rhine?"),
        # but one that names only the correct option gives the answer away.
        wrong = [option for option in options if option not in correct]
        if (
            question.format == "single"
            and not is_fixed_pair(options)
            and find_giveaway(question.question, correct) is not None
            and find_giveaway(question.question, wrong) is None
        ):
            raise ValueError(f"the question names only the correct option: {correct[0]!r}")
    expected = ", ".join(correct)
    if len(expected) > MAX_EXPECTED_ANSWER_LENGTH:
        raise ValueError("the correct options are too long")
    return question.model_copy(
        update={
            "options": options,
            "correct_options": correct,
            "expected_answer": expected,
            "accepted_answers": [],
        }
    )


def is_fixed_pair(options: list[str]) -> bool:
    """True/False, Yes/No and their translations."""
    keys = sorted(option.casefold() for option in options)
    return any(keys == sorted(fixed) for fixed in FIXED_ORDERS)


def words(text: str) -> str:
    """Lower case words separated by single spaces, padded so whole words can be matched."""
    return " " + " ".join(re.findall(r"\w+", text.casefold())) + " "


def find_giveaway(text: str, answers: list[str]) -> str | None:
    """The first answer that appears word for word in the text, if any."""
    text_words = words(text)
    for answer in answers:
        answer_words = words(answer)
        if len(answer_words.strip()) >= MIN_GIVEAWAY_LENGTH and answer_words in text_words:
            return answer
    return None


def shuffled(question: Question, rng: random.Random) -> Question:
    """The options shuffled: writers tend to put the correct one first, and the critic and
    the blind solver should not see that. True/False and Yes/No keep their usual order;
    an order question is never left in the correct order."""
    if not question.is_choice:
        return question
    keys = sorted(option.casefold() for option in question.options)
    for fixed in FIXED_ORDERS:
        if keys == sorted(fixed):
            ordered = sorted(question.options, key=lambda option: fixed.index(option.casefold()))
            return question.model_copy(update={"options": ordered})
    options = list(question.options)
    rng.shuffle(options)
    while question.format == "order" and options == question.correct_options:
        rng.shuffle(options)
    return question.model_copy(update={"options": options})
