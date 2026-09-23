"""Call one: turn a question seed into a trivia question with expected answers."""

import json
import re
import uuid
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.graph.model import QuestionSeed
from app.llm.call_log import CallLogger, LLMCallRecord
from app.llm.client import ChatRequest, LLMClient, timed_call
from app.llm.facts import format_seed
from app.llm.prompts import PromptTemplate

GENERATOR_TEMPERATURE = 0.8


class QuestionGenerationError(RuntimeError):
    """The generator produced no valid question within the allowed attempts."""


class NumericRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float
    max: float
    unit: str = Field(max_length=40)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.min > self.max:
            raise ValueError("numeric_range.min must not exceed numeric_range.max")
        return self


class GeneratedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=10, max_length=300)
    expected_answer: str = Field(min_length=1, max_length=200)
    accepted_answers: list[str] = Field(default_factory=list, max_length=20)
    numeric_range: NumericRange | None

    @model_validator(mode="after")
    def _answer_not_in_question(self) -> Self:
        answer = self.expected_answer.strip().casefold()
        if self.numeric_range is None and len(answer) > 2 and answer in self.question.casefold():
            raise ValueError("the question gives away the expected answer")
        return self


# Written out instead of generated from the model so it has no $ref indirections,
# which structured output implementations handle unevenly.
QUESTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "expected_answer": {"type": "string"},
        "accepted_answers": {"type": "array", "items": {"type": "string"}},
        "numeric_range": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        "min": {"type": "number"},
                        "max": {"type": "number"},
                        "unit": {"type": "string"},
                    },
                    "required": ["min", "max", "unit"],
                },
                {"type": "null"},
            ]
        },
    },
    "required": ["question", "expected_answer", "accepted_answers", "numeric_range"],
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
    # Clean up the accepted answers: trimmed, no empties, no duplicates of the expected one.
    seen = {question.expected_answer.strip().casefold()}
    accepted = []
    for answer in question.accepted_answers:
        text = answer.strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            accepted.append(text)
    return question.model_copy(
        update={
            "question": question.question.strip(),
            "expected_answer": question.expected_answer.strip(),
            "accepted_answers": accepted,
        }
    )


class QuestionGenerator:
    def __init__(
        self,
        client: LLMClient,
        model: str,
        prompt: PromptTemplate,
        call_logger: CallLogger,
        max_attempts: int = 2,
    ) -> None:
        self._client = client
        self._model = model
        self._prompt = prompt
        self._call_logger = call_logger
        self._max_attempts = max_attempts

    def generate(self, seed: QuestionSeed, *, run_id: uuid.UUID | None = None) -> GeneratedQuestion:
        request = ChatRequest(
            model=self._model,
            system=self._prompt.system,
            user=self._prompt.render_user(facts=format_seed(seed)),
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
                    question = parse_generated_question(outcome.raw_output)
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
