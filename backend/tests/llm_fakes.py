"""Test doubles for the LLM layer. No test may call the real Ollama API."""

from collections.abc import Iterable

from app.llm.call_log import LLMCallRecord
from app.llm.client import ChatRequest, LLMError
from app.llm.generator_prompt import PROMPT as GENERATOR_PROMPT
from app.llm.judge_prompt import PROMPT as JUDGE_PROMPT
from app.llm.prompts import PromptTemplate

_REAL_PROMPTS = {
    "generate_question": GENERATOR_PROMPT,
    "judge_answer": JUDGE_PROMPT,
}


class ScriptedClient:
    """Returns scripted outputs in order; an LLMError instance in the script is raised."""

    def __init__(self, outputs: Iterable[str | LLMError]) -> None:
        self._outputs = list(outputs)
        self.requests: list[ChatRequest] = []

    def chat(self, request: ChatRequest) -> str:
        self.requests.append(request)
        if not self._outputs:
            raise AssertionError("ScriptedClient received more calls than scripted")
        output = self._outputs.pop(0)
        if isinstance(output, LLMError):
            raise output
        return output


class ListCallLogger:
    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def log(self, record: LLMCallRecord) -> None:
        self.records.append(record)


def real_prompt(name: str) -> PromptTemplate:
    """The real prompts, so tests also check that they render."""
    return _REAL_PROMPTS[name]
