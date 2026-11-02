"""One LLM call with a JSON reply: parsed, logged per attempt, retried once on bad output.

Used by the critic and the solver of the question pool. The generator and the judge keep
their own loops, which have rules of their own (retry notes, strict true or false).
"""

from collections.abc import Callable

from app.llm.call_log import CallLogger, LLMCallRecord, Purpose
from app.llm.client import ChatRequest, LLMClient, timed_call


class StructuredCallError(RuntimeError):
    """No valid reply within the allowed attempts."""


def call_structured[T](
    client: LLMClient,
    request: ChatRequest,
    parse: Callable[[str], T],
    *,
    purpose: Purpose,
    call_logger: CallLogger,
    max_attempts: int = 2,
) -> T:
    """parse raises ValueError on invalid output; its result is logged as parsed."""
    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        outcome = timed_call(client, request)
        result: T | None = None
        error = outcome.error
        if outcome.raw_output is not None:
            try:
                result = parse(outcome.raw_output)
            except ValueError as parse_error:
                error = str(parse_error)
        call_logger.log(
            LLMCallRecord(
                purpose=purpose,
                model=request.model,
                attempt=attempt,
                request=request.to_log(),
                raw_output=outcome.raw_output,
                parsed=_loggable(result),
                error=error,
                latency_ms=outcome.latency_ms,
            )
        )
        if result is not None:
            return result
        errors.append(error or "unknown error")
    raise StructuredCallError("; ".join(errors))


def _loggable(result: object) -> object:
    dump = getattr(result, "model_dump", None)
    return dump() if callable(dump) else result
