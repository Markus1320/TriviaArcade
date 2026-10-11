"""Call one: turn a question seed into a trivia question with expected answers."""

import json
import random
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.graph.model import QuestionSeed
from app.llm.call_log import CallLogger, LLMCallRecord
from app.llm.client import ChatRequest, LLMClient, timed_call
from app.llm.facts import format_seed
from app.llm.generator_prompt import pick_examples, pick_true_false_hint
from app.llm.prompts import PromptTemplate

GENERATOR_TEMPERATURE = 0.8


class QuestionGenerationError(RuntimeError):
    """The generator produced no valid question within the allowed attempts."""


QuestionFormat = Literal["free", "single", "multiple"]

# Options per choice format. A single choice needs at least one wrong option; a multiple
# choice needs at least two correct ones and one wrong one, so "all of them" and "just
# one" are never the answer.
OPTION_LIMITS: dict[str, tuple[int, int]] = {"single": (2, 5), "multiple": (3, 6)}
MAX_OPTION_LENGTH = 80
MAX_EXPECTED_ANSWER_LENGTH = 200
# Answers shorter than this are not checked by the giveaway check ("UN", "No", "5").
MIN_GIVEAWAY_LENGTH = 3
# Kept in this order instead of being shuffled.
FIXED_OPTION_ORDERS = (("true", "false"), ("yes", "no"))


class GeneratedQuestion(BaseModel):
    """A question in one of three formats.

    - free: the player types the answer; expected_answer and accepted_answers are used
      by the judge.
    - single, multiple: the player picks from options; correct_options is checked by
      code. expected_answer is derived (the correct options, joined) for display and logs.
    """

    model_config = ConfigDict(extra="forbid")

    format: QuestionFormat = "free"
    question: str = Field(min_length=10, max_length=300)
    options: list[str] = Field(default_factory=list, max_length=10)
    correct_options: list[str] = Field(default_factory=list, max_length=10)
    expected_answer: str = Field(default="", max_length=MAX_EXPECTED_ANSWER_LENGTH)
    accepted_answers: list[str] = Field(default_factory=list, max_length=20)
    # Shown to the player after answering. Optional on purpose: a missing explanation is
    # not worth rejecting an otherwise good question.
    explanation: str = Field(default="", max_length=400)

    @property
    def is_choice(self) -> bool:
        return self.format != "free"

    @property
    def correct_indices(self) -> list[int]:
        """Positions of the correct options within options."""
        return [i for i, option in enumerate(self.options) if option in self.correct_options]


# Written out instead of generated from the model so it has no $ref indirections,
# which structured output implementations handle unevenly.
QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "format": {"type": "string", "enum": ["free", "single", "multiple"]},
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "correct_options": {"type": "array", "items": {"type": "string"}},
        "expected_answer": {"type": "string"},
        "accepted_answers": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": ["format", "question", "explanation"],
}


_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.DOTALL)


def extract_json_object(raw: str) -> str:
    """Return the JSON object text from generator output.

    Some models ignore structured output and wrap the JSON in a Markdown code fence or
    add a sentence around it, so both are tolerated. The raw output is logged unchanged.
    """
    text = raw.strip()
    fenced = _CODE_FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
    return text


def parse_generated_question(raw: str) -> GeneratedQuestion:
    """Parse and validate generator output. Raises ValueError when invalid."""
    try:
        data = json.loads(extract_json_object(raw))
    except json.JSONDecodeError as error:
        raise ValueError(f"output is not valid JSON: {error}") from error
    try:
        question = GeneratedQuestion.model_validate(data)
    except ValidationError as error:
        raise ValueError(f"output does not match the schema: {error}") from error
    question = question.model_copy(
        update={
            "question": question.question.strip(),
            "explanation": question.explanation.strip(),
        }
    )
    return _clean_choice(question) if question.is_choice else _clean_free(question)


def _clean_free(question: GeneratedQuestion) -> GeneratedQuestion:
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


def _clean_choice(question: GeneratedQuestion) -> GeneratedQuestion:
    options = [option.strip() for option in question.options]
    if any(not option or len(option) > MAX_OPTION_LENGTH for option in options):
        raise ValueError(f"options must have 1 to {MAX_OPTION_LENGTH} characters")
    by_key = {option.casefold(): option for option in options}
    if len(by_key) != len(options):
        raise ValueError("options must be distinct")
    low, high = OPTION_LIMITS[question.format]
    if not low <= len(options) <= high:
        raise ValueError(f"a {question.format} choice question needs {low} to {high} options")

    correct_keys = {option.strip().casefold() for option in question.correct_options}
    unknown = correct_keys - set(by_key)
    if unknown:
        raise ValueError(f"correct_options are not among the options: {sorted(unknown)}")
    correct = [option for option in options if option.casefold() in correct_keys]
    if question.format == "single" and len(correct) != 1:
        raise ValueError("a single choice question needs exactly one correct option")
    if question.format == "multiple" and not 2 <= len(correct) < len(options):
        raise ValueError(
            "a multiple choice question needs at least two correct and one wrong option"
        )
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


def _words(text: str) -> str:
    """Lower case words separated by single spaces, padded so whole words can be matched."""
    return " " + " ".join(re.findall(r"\w+", text.casefold())) + " "


def find_giveaway(question: str, answers: list[str]) -> str | None:
    """The first answer that appears word for word in the question, if any.

    Only meaningful for free questions: choice questions show their answers on purpose.
    """
    question_words = _words(question)
    for answer in answers:
        answer_words = _words(answer)
        if len(answer_words.strip()) >= MIN_GIVEAWAY_LENGTH and answer_words in question_words:
            return answer
    return None


def shuffle_options(question: GeneratedQuestion, rng: random.Random) -> GeneratedQuestion:
    """Shuffle the options of a choice question; models tend to put the correct one first.

    True/False and Yes/No keep their usual order.
    """
    if not question.is_choice:
        return question
    keys = [option.casefold() for option in question.options]
    for fixed in FIXED_OPTION_ORDERS:
        if sorted(keys) == sorted(fixed):
            ordered = sorted(question.options, key=lambda option: fixed.index(option.casefold()))
            return question.model_copy(update={"options": ordered})
    options = list(question.options)
    rng.shuffle(options)
    return question.model_copy(update={"options": options})


class QuestionGenerator:
    def __init__(
        self,
        client: LLMClient,
        model: str,
        prompt: PromptTemplate,
        call_logger: CallLogger,
        max_attempts: int = 2,
        rng: random.Random | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._prompt = prompt
        self._call_logger = call_logger
        self._max_attempts = max_attempts
        self._rng = rng or random.Random()

    def generate(self, seed: QuestionSeed, *, run_id: uuid.UUID | None = None) -> GeneratedQuestion:
        request = ChatRequest(
            model=self._model,
            system=self._prompt.system,
            user=self._prompt.render_user(
                facts=format_seed(seed),
                examples=pick_examples(),
                true_false_hint=pick_true_false_hint(),
            ),
            json_schema=QUESTION_SCHEMA,
            temperature=GENERATOR_TEMPERATURE,
        )
        errors: list[str] = []
        for attempt in range(1, self._max_attempts + 1):
            outcome = timed_call(self._client, request)
            question: GeneratedQuestion | None = None
            error = outcome.error
            if outcome.raw_output is not None:
                try:
                    question = shuffle_options(
                        parse_generated_question(outcome.raw_output), self._rng
                    )
                except ValueError as parse_error:
                    error = str(parse_error)
            self._call_logger.log(
                LLMCallRecord(
                    purpose="generate",
                    model=self._model,
                    attempt=attempt,
                    request=request.to_log(),
                    raw_output=outcome.raw_output,
                    parsed=question.model_dump() if question else None,
                    error=error,
                    latency_ms=outcome.latency_ms,
                    run_id=run_id,
                )
            )
            if question is not None:
                return question
            errors.append(error or "unknown error")
        raise QuestionGenerationError("; ".join(errors))
