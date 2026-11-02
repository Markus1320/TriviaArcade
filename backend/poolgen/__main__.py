"""Fill the question pool of one language.

Never part of CI: it calls the real LLM and needs Neo4j (and PostgreSQL for the call log).

    docker compose run --rm poolgen python -m poolgen --language en --walks 10

Each walk gives one accepted or one rejected record, appended to the pool files at once,
so the run can be stopped and started again at any time. When the provider's usage limit
is reached, the walk in progress is dropped and the run waits (--wait-hours).
"""

import argparse
import logging
import random
import sys
import time
from pathlib import Path
from typing import get_args

from app.config import Settings, get_settings
from app.db.engine import get_session_factory
from app.graph.factory import build_walker
from app.graph.walk import NoQuestionSeedError
from app.languages import Language
from app.llm.call_log import CallLogger, NullCallLogger, SqlCallLogger
from app.llm.critic import QuestionCritic
from app.llm.critic_prompt import PROMPT as critic_prompt
from app.llm.generator import QuestionGenerator
from app.llm.generator_prompt import PROMPT as generator_prompt
from app.llm.ollama import OllamaClient
from app.llm.solver import BlindSolver
from app.llm.solver_prompt import PROMPT as solver_prompt
from app.pool.records import (
    DEFAULT_DIR,
    PoolQuestion,
    Rejection,
    append_record,
    pool_path,
    read_records,
    rejected_path,
)
from poolgen.index import PoolIndex
from poolgen.pipeline import (
    CountingClient,
    PipelineSettings,
    PoolPipeline,
    UsageLimitReached,
)

# Walks failing in a row for technical reasons before the run waits as for a usage limit.
MAX_FAILURES_IN_A_ROW = 5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m poolgen")
    parser.add_argument("--language", choices=get_args(Language), required=True)
    parser.add_argument("--walks", type=int, required=True, help="walks to process")
    parser.add_argument("--dir", type=Path, default=Path(DEFAULT_DIR), help="pool directory")
    parser.add_argument("--seed", type=int, help="random seed for reproducible walks")
    parser.add_argument("--types", help="only start from these entity types, comma separated")
    parser.add_argument("--max-rounds", type=int, default=PipelineSettings.max_rounds)
    parser.add_argument("--answer-cap", type=int, default=PipelineSettings.answer_cap)
    parser.add_argument("--wait-hours", type=float, default=5.0, help="pause at a usage limit")
    parser.add_argument("--no-log", action="store_true", help="do not log calls to PostgreSQL")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    settings = get_settings()
    missing = _missing_settings(settings)
    if missing:
        print(f"set {', '.join(missing)} in .env", file=sys.stderr)
        return 2
    call_logger: CallLogger = (
        NullCallLogger() if args.no_log else SqlCallLogger(get_session_factory())
    )
    pool_file, rejected_file = (
        pool_path(args.dir, args.language),
        rejected_path(args.dir, args.language),
    )
    index = PoolIndex.build(
        read_records(pool_file, PoolQuestion), read_records(rejected_file, Rejection)
    )
    print(f"Pool {pool_file}: {index.accepted} questions, {len(index.used_starts)} starts used")

    pipeline, ollama = _build_pipeline(settings, call_logger, index, args)
    start_types = frozenset(t.strip() for t in args.types.split(",")) if args.types else frozenset()
    walker = build_walker(settings, random.Random(args.seed), start_types)
    failures = 0
    walk = 0
    try:
        while walk < args.walks:
            try:
                seed = walker.walk(exclude_start_ids=index.used_starts)
            except NoQuestionSeedError as error:
                print(f"No more walks: {error}")
                break
            try:
                record = pipeline.build(seed, args.language)
            except UsageLimitReached as error:
                _wait(f"usage limit reached ({error})", args.wait_hours)
                continue
            walk += 1
            if isinstance(record, PoolQuestion):
                append_record(pool_file, record)
                index.add(record)
                failures = 0
                print(
                    f"[{walk}/{args.walks}] ok    {record.start_type}: "
                    f"{record.question.format} {record.question.question} "
                    f"({len(record.rounds)} drafts, {record.calls} calls, {record.seconds:.0f}s)"
                )
                continue
            append_record(rejected_file, record)
            index.add_rejection(record)
            print(
                f"[{walk}/{args.walks}] reject {record.start_type}: {record.reason[:160]} "
                f"({record.calls} calls, {record.seconds:.0f}s)"
            )
            failures = failures + 1 if record.technical else 0
            if failures >= MAX_FAILURES_IN_A_ROW:
                _wait(f"{failures} technical failures in a row", args.wait_hours)
                failures = 0
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        ollama.close()
    print(f"Pool {pool_file}: {index.accepted} questions")
    return 0


def _missing_settings(settings: Settings) -> list[str]:
    return [
        name
        for name, value in [
            ("OLLAMA_API_KEY", settings.ollama_api_key),
            ("OLLAMA_BASE_URL", settings.ollama_base_url),
            ("LLM_GENERATOR_MODEL", settings.llm_generator_model),
            ("LLM_CRITIC_MODEL", settings.llm_critic_model),
        ]
        if not value
    ]


def _build_pipeline(
    settings: Settings, call_logger: CallLogger, index: PoolIndex, args: argparse.Namespace
) -> tuple[PoolPipeline, OllamaClient]:
    assert settings.ollama_api_key and settings.ollama_base_url  # checked by the caller
    assert settings.llm_generator_model and settings.llm_critic_model
    ollama = OllamaClient(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key.get_secret_value(),
        timeout_seconds=max(settings.llm_timeout_seconds, 300),
    )
    client = CountingClient(ollama)
    generator = QuestionGenerator(
        client, settings.llm_generator_model, generator_prompt, call_logger, think=True
    )
    critic = QuestionCritic(client, settings.llm_critic_model, critic_prompt, call_logger)
    solver = BlindSolver(client, settings.llm_critic_model, solver_prompt, call_logger)
    pipeline = PoolPipeline(
        generator,
        critic,
        solver,
        index,
        client,
        generator_model=settings.llm_generator_model,
        settings=PipelineSettings(max_rounds=args.max_rounds, answer_cap=args.answer_cap),
    )
    return pipeline, ollama


def _wait(reason: str, hours: float) -> None:
    resume = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + hours * 3600))
    print(f"{reason}; the walk in progress is dropped. Waiting until {resume}.", flush=True)
    time.sleep(hours * 3600)


if __name__ == "__main__":
    sys.exit(main())
