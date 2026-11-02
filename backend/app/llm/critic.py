"""The critic of the question pool: approves a draft, asks for a revision or rejects it."""

import json
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.llm.call_log import CallLogger
from app.llm.client import ChatRequest, LLMClient, Think
from app.llm.generator import NOTE_FIELDS, GeneratedQuestion, extract_json_object
from app.llm.prompts import PromptTemplate
from app.llm.structured import call_structured

CRITIC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["approve", "revise", "reject"]},
        "feedback": {"type": "string"},
    },
    "required": ["verdict", "feedback"],
}

# Language codes as the critic reads them.
LANGUAGE_NAMES = {"en": "English", "de": "German"}


class CriticVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    verdict: Literal["approve", "revise", "reject"]
    feedback: str = Field(default="", max_length=2000)


def parse_critic_verdict(raw: str) -> CriticVerdict:
    try:
        data = json.loads(extract_json_object(raw))
        verdict = CriticVerdict.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ValueError(f"critic output is invalid: {error}") from error
    if verdict.verdict != "approve" and not verdict.feedback.strip():
        raise ValueError("a revise or reject verdict needs feedback")
    return verdict.model_copy(update={"feedback": verdict.feedback.strip()})


def draft_for_review(question: GeneratedQuestion) -> str:
    """The draft as JSON without the writer's notes, which the critic judges unseen."""
    data = question.model_dump(exclude=set(NOTE_FIELDS))
    if question.is_choice:
        data.pop("expected_answer")
        data.pop("accepted_answers")
    else:
        data.pop("options")
        data.pop("correct_options")
    return json.dumps(data, ensure_ascii=False, indent=1)


def format_existing(questions: Sequence[str]) -> str:
    return "\n".join(f"- {question}" for question in questions) if questions else "(none)"


class QuestionCritic:
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

    @property
    def model(self) -> str:
        return self._model

    def review(
        self,
        question: GeneratedQuestion,
        *,
        facts: str,
        existing: Sequence[str],
        language: str,
    ) -> CriticVerdict:
        """Raises StructuredCallError when the critic gives no valid verdict."""
        request = ChatRequest(
            model=self._model,
            system=self._prompt.system,
            user=self._prompt.render_user(
                game_language=LANGUAGE_NAMES.get(language, language),
                facts=facts,
                existing=format_existing(existing),
                draft=draft_for_review(question),
            ),
            json_schema=CRITIC_SCHEMA,
            think=self._think,
        )
        return call_structured(
            self._client,
            request,
            parse_critic_verdict,
            purpose="critic",
            call_logger=self._call_logger,
        )
