"""The LLMClient protocol. Game logic depends on this, never on a concrete provider."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(RuntimeError):
    """A technical failure: network, HTTP error, malformed provider response."""


@dataclass(frozen=True)
class ChatRequest:
    model: str
    system: str
    user: str
    # JSON schema the provider must enforce on the output (structured output).
    json_schema: dict[str, Any] | None = None
    temperature: float | None = None

    def to_log(self) -> dict[str, Any]:
        """Everything needed to replay the call; contains no credentials."""
        return {
            "system": self.system,
            "user": self.user,
            "json_schema": self.json_schema,
            "temperature": self.temperature,
        }


class LLMClient(Protocol):
    def chat(self, request: ChatRequest) -> str:
        """Return the raw text output. Raise LLMError on technical failures."""
        ...


@dataclass(frozen=True)
class CallOutcome:
    raw_output: str | None
    error: str | None
    latency_ms: int


def timed_call(
    client: LLMClient,
    request: ChatRequest,
    clock: Callable[[], float] = time.perf_counter,
) -> CallOutcome:
    start = clock()
    try:
        raw = client.chat(request)
    except LLMError as error:
        return CallOutcome(None, str(error), _elapsed_ms(clock, start))
    return CallOutcome(raw, None, _elapsed_ms(clock, start))


def _elapsed_ms(clock: Callable[[], float], start: float) -> int:
    return round((clock() - start) * 1000)
