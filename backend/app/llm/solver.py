"""The blind solver of the question pool: answers a question without seeing its answer.

For choice questions it shows whether the question has the one answer the writer meant.
For free questions it also lists every form of the answer that must count as correct,
which the pool keeps for judging typed answers without an LLM.
"""

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.call_log import CallLogger
from app.llm.client import ChatRequest, LLMClient, Think
from app.llm.critic import LANGUAGE_NAMES
from app.llm.generator import GeneratedQuestion, extract_json_object
from app.llm.prompts import PromptTemplate
from app.llm.structured import call_structured

SOLVER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"answers": {"type": "array", "items": {"type": "string"}}},
    "required": ["answers"],
}


class SolverAnswers(BaseModel):
    model_config = ConfigDict(extra="ignore")

    answers: list[str] = Field(max_length=100)


def parse_solver_answers(raw: str) -> list[str]:
    try:
        data = json.loads(extract_json_object(raw))
        parsed = SolverAnswers.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"solver output is invalid: {error}") from error
    answers: list[str] = []
    for answer in parsed.answers:
        text = answer.strip()
        if text and text not in answers:
            answers.append(text)
    return answers


class BlindSolver:
    def __init__(
        self,
        client: LLMClient,
        model: str,
        prompt: PromptTemplate,
        call_logger: CallLogger,
        think: Think | None = "high",
    ) -> None:
        self._client = client
        self._model = model
        self._prompt = prompt
        self._call_logger = call_logger
        self._think = think

    def solve(self, question: GeneratedQuestion, *, language: str) -> list[str]:
        """Raises StructuredCallError when the solver gives no valid reply."""
        options = "".join(f"- {option}\n" for option in question.options)
        request = ChatRequest(
            model=self._model,
            system=self._prompt.system,
            user=self._prompt.render_user(
                game_language=LANGUAGE_NAMES.get(language, language),
                format=question.format,
                question=question.question,
                options=f"Options:\n{options}" if options else "",
            ),
            json_schema=SOLVER_SCHEMA,
            think=self._think,
        )
        return call_structured(
            self._client,
            request,
            parse_solver_answers,
            purpose="solve",
            call_logger=self._call_logger,
        )
