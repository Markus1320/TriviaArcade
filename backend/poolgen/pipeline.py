"""From one walk to one pool question: write, review, revise, solve blind.

1. The writer (the game's generator, with thinking) drafts a question. It sees the
   questions already in the pool about the walk's entities.
2. Code checks: the same typed answer may not be in the pool too often.
3. The critic approves, asks for a revision (back to 1 with its feedback) or rejects.
   After max_rounds drafts without approval the walk is rejected.
4. The blind solver answers the approved question without seeing the answer. A choice
   question passes when it picks exactly the correct options; a free question when its
   answers contain the expected one or an accepted one. Its answers are kept: they are the
   forms a typed answer may take, for judging without an LLM.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.game.matcher import normalize_answer
from app.graph.model import QuestionSeed
from app.llm.client import ChatRequest, LLMClient, LLMRateLimitError
from app.llm.critic import QuestionCritic, draft_for_review
from app.llm.facts import format_seed
from app.llm.generator import GeneratedQuestion, QuestionGenerationError, QuestionGenerator
from app.llm.solver import BlindSolver
from app.llm.structured import StructuredCallError
from poolgen.index import PoolIndex, answer_aliases, mentioned_entities
from poolgen.records import PoolQuestion, Rejection, Round, question_id

EXISTING_NOTE = (
    "Questions that already exist about these entities. Do not ask their facts again, in "
    "any format or wording; ask about something different:\n{questions}"
)
REVISION_NOTE = (
    "Your previous draft:\n{draft}\n\nA strict editor reviewed it:\n{feedback}\n\n"
    "Write an improved question that follows the feedback. You may change the format or "
    "ask about another fact."
)
ANSWER_USED_NOTE = (
    "The answer {answer!r} is already the answer of {uses} questions in the pool. Ask about "
    "something with another answer."
)


class UsageLimitReached(Exception):
    """The provider's usage limit was hit. Not an LLMError, so no call site retries it:
    the walk in progress is dropped and the run waits."""


class CountingClient:
    """Counts calls and turns the provider's rate limit into UsageLimitReached."""

    def __init__(self, client: LLMClient) -> None:
        self._client = client
        self.calls = 0

    def chat(self, request: ChatRequest) -> str:
        self.calls += 1
        try:
            return self._client.chat(request)
        except LLMRateLimitError as error:
            raise UsageLimitReached(str(error)) from error


@dataclass(frozen=True)
class PipelineSettings:
    max_rounds: int = 3
    answer_cap: int = 2


def utc_now() -> datetime:
    return datetime.now(UTC)


class PoolPipeline:
    def __init__(
        self,
        generator: QuestionGenerator,
        critic: QuestionCritic,
        solver: BlindSolver,
        index: PoolIndex,
        client: CountingClient,
        *,
        generator_model: str,
        settings: PipelineSettings | None = None,
        clock: Callable[[], datetime] = utc_now,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._generator = generator
        self._critic = critic
        self._solver = solver
        self._index = index
        self._client = client
        self._generator_model = generator_model
        self._settings = settings or PipelineSettings()
        self._clock = clock
        self._timer = timer

    def build(self, seed: QuestionSeed, language: str) -> PoolQuestion | Rejection:
        """Raises UsageLimitReached when the provider refuses calls."""
        started, calls_before = self._timer(), self._client.calls
        facts = format_seed(seed)
        entity_ids = [node.wikidata_id for node in seed.nodes]
        existing = self._index.related(entity_ids)
        rounds: list[Round] = []

        def reject(reason: str, technical: bool = False) -> Rejection:
            return Rejection(
                language=language,
                created_at=self._clock(),
                start_entity=seed.start.wikidata_id,
                start_type=seed.start.entity_type,
                entities=entity_ids,
                facts=facts,
                reason=reason,
                technical=technical,
                rounds=rounds,
                seconds=round(self._timer() - started, 1),
                calls=self._client.calls - calls_before,
            )

        approved: tuple[GeneratedQuestion, str] | None = None
        revision: tuple[GeneratedQuestion, str] | None = None
        for _ in range(self._settings.max_rounds):
            try:
                result = self._generator.generate(
                    seed, language=language, context=_context(existing, revision)
                )
            except QuestionGenerationError as error:
                return reject(f"writer failed: {error}", technical=True)
            draft = result.question
            uses = self._index.answer_uses(draft)
            if uses >= self._settings.answer_cap:
                note = ANSWER_USED_NOTE.format(answer=draft.expected_answer, uses=uses)
                rounds.append(Round(question=draft, verdict="code", feedback=note))
                revision = (draft, note)
                continue
            try:
                verdict = self._critic.review(
                    draft, facts=facts, existing=existing, language=language
                )
            except StructuredCallError as error:
                return reject(f"critic failed: {error}", technical=True)
            rounds.append(Round(question=draft, verdict=verdict.verdict, feedback=verdict.feedback))
            if verdict.verdict == "approve":
                approved = (draft, result.prompt)
                break
            if verdict.verdict == "reject":
                return reject(f"critic rejected: {verdict.feedback}")
            revision = (draft, verdict.feedback)
        if approved is None:
            return reject(f"not approved after {self._settings.max_rounds} drafts")

        question, prompt = approved
        try:
            solved = self._solver.solve(question, language=language)
        except StructuredCallError as error:
            return reject(f"solver failed: {error}", technical=True)
        miss = solver_miss(question, solved)
        if miss:
            return reject(f"blind solve: {miss} (solver: {solved})")

        return PoolQuestion(
            id=question_id(language, question.question),
            language=language,
            created_at=self._clock(),
            start_entity=seed.start.wikidata_id,
            start_type=seed.start.entity_type,
            entities=entity_ids,
            mentioned=mentioned_entities(seed, question),
            facts=facts,
            question=question,
            solver_answers=solved,
            graph_aliases=answer_aliases(seed, question),
            generator_model=self._generator_model,
            critic_model=self._critic.model,
            prompt=prompt,
            rounds=rounds,
            seconds=round(self._timer() - started, 1),
            calls=self._client.calls - calls_before,
        )


def _context(existing: Sequence[str], revision: tuple[GeneratedQuestion, str] | None) -> str:
    parts = []
    if existing:
        parts.append(EXISTING_NOTE.format(questions="\n".join(f"- {q}" for q in existing)))
    if revision is not None:
        draft, feedback = revision
        parts.append(REVISION_NOTE.format(draft=draft_for_review(draft), feedback=feedback))
    return "\n\n".join(parts)


def solver_miss(question: GeneratedQuestion, solved: Sequence[str]) -> str | None:
    """Why the blind solver's answers do not confirm the question, or None if they do."""
    found = [normalize_answer(answer) for answer in solved]
    if question.format == "order":
        expected = [normalize_answer(option) for option in question.correct_options]
        return None if found == expected else "sorted differently"
    if question.is_choice:
        expected_set = {normalize_answer(option) for option in question.correct_options}
        return None if set(found) == expected_set else "picked other options"
    answers = [question.expected_answer, *question.accepted_answers]
    if any(normalize_answer(answer) in found for answer in answers):
        return None
    return "the expected answer is not among its answers"
