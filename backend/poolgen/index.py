"""What the pool already holds, to keep new questions from repeating it.

Three layers:
- Every start entity is walked at most once per pool (accepted or rejected).
- Questions already in the pool about the walk's entities are shown to the writer and the
  critic, so they ask about something else.
- The same typed answer is allowed at most answer_cap times.
"""

from collections import Counter
from collections.abc import Iterable, Sequence

from app.game.matcher import normalize_answer
from app.graph.model import GraphNode, QuestionSeed
from app.llm.generator import GeneratedQuestion, find_giveaway
from app.pool.records import PoolQuestion, Rejection


def summary(question: GeneratedQuestion) -> str:
    return f"{question.question} [{question.expected_answer}]"


def node_names(node: GraphNode) -> list[str]:
    return [node.label, *node.aliases]


def mentioned_entities(seed: QuestionSeed, question: GeneratedQuestion) -> list[str]:
    """The walk's entities named in the question, its answers or its options."""
    text = " ".join(
        [
            question.question,
            question.expected_answer,
            *question.accepted_answers,
            *question.options,
        ]
    )
    return [
        node.wikidata_id for node in seed.nodes if find_giveaway(text, node_names(node)) is not None
    ]


def answer_aliases(seed: QuestionSeed, question: GeneratedQuestion) -> list[str]:
    """Label and aliases of the entity a free question asks for, if it is in the walk."""
    if question.is_choice:
        return []
    answers = {normalize_answer(a) for a in [question.expected_answer, *question.accepted_answers]}
    for node in seed.nodes:
        names = node_names(node)
        if any(normalize_answer(name) in answers for name in names):
            return names
    return []


class PoolIndex:
    def __init__(self, related_limit: int = 10) -> None:
        self.used_starts: set[str] = set()
        self._by_entity: dict[str, list[str]] = {}
        self._answers: Counter[str] = Counter()
        self._related_limit = related_limit
        self.accepted = 0

    @classmethod
    def build(cls, accepted: Iterable[PoolQuestion], rejected: Iterable[Rejection]) -> "PoolIndex":
        index = cls()
        for question in accepted:
            index.add(question)
        for rejection in rejected:
            index.add_rejection(rejection)
        return index

    def add(self, record: PoolQuestion) -> None:
        self.accepted += 1
        self.used_starts.add(record.start_entity)
        text = summary(record.question)
        for entity in record.mentioned:
            self._by_entity.setdefault(entity, []).append(text)
        if not record.question.is_choice:
            self._answers[normalize_answer(record.question.expected_answer)] += 1

    def add_rejection(self, record: Rejection) -> None:
        if not record.technical:
            self.used_starts.add(record.start_entity)

    def related(self, entity_ids: Sequence[str]) -> list[str]:
        """Questions in the pool that name one of these entities, the start entity first."""
        found: list[str] = []
        for entity in entity_ids:
            for text in self._by_entity.get(entity, []):
                if text not in found:
                    found.append(text)
        return found[: self._related_limit]

    def answer_uses(self, question: GeneratedQuestion) -> int:
        if question.is_choice:
            return 0
        return self._answers[normalize_answer(question.expected_answer)]
