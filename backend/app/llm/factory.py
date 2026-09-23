"""Builds the generator and judge from the application settings."""

from dataclasses import dataclass

from app.config import Settings
from app.llm.call_log import CallLogger
from app.llm.generator import QuestionGenerator
from app.llm.judge import AnswerJudge
from app.llm.ollama import OllamaClient
from app.llm.prompts import load_prompt


class LLMNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMComponents:
    client: OllamaClient
    generator: QuestionGenerator
    judge: AnswerJudge


def build_llm_components(settings: Settings, call_logger: CallLogger) -> LLMComponents:
    missing = [
        name
        for name, value in [
            ("OLLAMA_API_KEY", settings.ollama_api_key),
            ("OLLAMA_BASE_URL", settings.ollama_base_url),
            ("LLM_GENERATOR_MODEL", settings.llm_generator_model),
            ("LLM_JUDGE_MODEL", settings.llm_judge_model),
        ]
        if not value
    ]
    if missing:
        raise LLMNotConfiguredError(f"set {', '.join(missing)} in .env")
    assert settings.ollama_api_key and settings.ollama_base_url  # narrowed for mypy
    assert settings.llm_generator_model and settings.llm_judge_model

    client = OllamaClient(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key.get_secret_value(),
        timeout_seconds=settings.llm_timeout_seconds,
    )
    generator = QuestionGenerator(
        client, settings.llm_generator_model, load_prompt("generate_question"), call_logger
    )
    judge = AnswerJudge(client, settings.llm_judge_model, load_prompt("judge_answer"), call_logger)
    return LLMComponents(client=client, generator=generator, judge=judge)
