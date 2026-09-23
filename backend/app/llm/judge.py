"""Call two: judge a player's answer, independent of the generator call."""

import json
import re
import uuid
from dataclasses import dataclass

from app.llm.call_log import CallLogger, LLMCallRecord
from app.llm.client import ChatRequest, LLMClient, timed_call
from app.llm.generator import NumericRange
from app.llm.prompts import PromptTemplate

MAX_ANSWER_LENGTH = 200
JUDGE_TEMPERATURE = 0.0

# Structured output restricted to a bare JSON boolean: the model can only say true or false.
VERDICT_SCHEMA = {"type": "boolean"}

_DELIMITER_PATTERN = re.compile(r"</?\s*player_answer\s*>", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


class JudgeUnavailableError(RuntimeError):
    """The judge failed technically. The run must be paused, never ended."""


@dataclass(frozen=True)
class JudgeInput:
    question: str
    expected_answer: str
    accepted_answers: tuple[str, ...]
    numeric_range: NumericRange | None


def sanitize_answer(answer: str) -> str:
    """Prepare untrusted player input for the prompt.

    Removes anything that looks like the answer delimiters, collapses whitespace
    (including newlines) and cuts the text to MAX_ANSWER_LENGTH characters.
    """
    text = _DELIMITER_PATTERN.sub(" ", answer)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:MAX_ANSWER_LENGTH]


def parse_verdict(raw: str) -> bool:
    """Accept exactly "true" or "false" (surrounding whitespace ignored), nothing else."""
    text = raw.strip()
    if text == "true":
        return True
    if text == "false":
        return False
    raise ValueError(f"judge output is not exactly true or false: {raw[:100]!r}")


def _format_range(numeric_range: NumericRange | None) -> str:
    if numeric_range is None:
        return "none (not a numeric question)"
    return f"from {numeric_range.min:g} to {numeric_range.max:g} {numeric_range.unit}".strip()


class AnswerJudge:
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

    def judge(
        self, item: JudgeInput, player_answer: str, *, run_id: uuid.UUID | None = None
    ) -> bool:
        answer = sanitize_answer(player_answer)
        if not answer:
            raise ValueError("the player answer is empty")
        request = ChatRequest(
            model=self._model,
            system=self._prompt.system,
            user=self._prompt.render_user(
                question=item.question,
                expected_answer=item.expected_answer,
                accepted_answers=json.dumps(list(item.accepted_answers), ensure_ascii=False),
                numeric_range=_format_range(item.numeric_range),
                player_answer=answer,
            ),
            json_schema=VERDICT_SCHEMA,
            temperature=JUDGE_TEMPERATURE,
        )
        errors: list[str] = []
        for attempt in range(1, self._max_attempts + 1):
            outcome = timed_call(self._client, request)
            verdict: bool | None = None
            error = outcome.error
            if outcome.raw_output is not None:
                try:
                    verdict = parse_verdict(outcome.raw_output)
                except ValueError as parse_error:
                    error = str(parse_error)
            self._call_logger.log(
                LLMCallRecord(
                    purpose="judge",
                    model=self._model,
                    attempt=attempt,
                    request=request.to_log(),
                    raw_output=outcome.raw_output,
                    parsed=verdict,
                    error=error,
                    latency_ms=outcome.latency_ms,
                    run_id=run_id,
                )
            )
            if verdict is not None:
                return verdict
            errors.append(error or "unknown error")
        raise JudgeUnavailableError("; ".join(errors))
