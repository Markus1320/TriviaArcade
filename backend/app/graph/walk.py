"""Random walk that picks the facts for one question.

1. Only the most famous share of each entity type takes part (WalkSettings.top_share).
   Fame is compared within a type, because sitelink counts differ a lot between types:
   a famous battle has fewer sitelinks than a mid-sized city.
2. Pick an entity type uniformly at random, then a random entity of that type. Picking the
   type first keeps large types (cities, people) from dominating the questions.
3. Skip starting nodes already used in the current run.
4. Walk min_hops to max_hops random hops to entities not visited yet.

All randomness comes from the injected random.Random, so walks are reproducible in tests.
"""

import random
from collections.abc import Collection
from dataclasses import dataclass, replace

from app.graph.model import GraphEdge, GraphNode, QuestionSeed
from app.graph.repository import FameThresholds, GraphRepository

# Fame labels for the generator, from the most famous share of each type downwards.
# Entities below the last share get FAME_DEFAULT_LABEL.
FAME_LEVELS: tuple[tuple[float, str], ...] = ((0.1, "world famous"), (0.3, "well known"))
FAME_DEFAULT_LABEL = "known to fans"


class NoQuestionSeedError(RuntimeError):
    """No usable starting node was found."""


@dataclass(frozen=True)
class WalkSettings:
    min_hops: int = 1
    max_hops: int = 2
    # Share of each entity type, most famous first, that walks may visit. 1.0 = all.
    # The cutoff is the type's (1 - top_share) percentile of sitelinks, boundary included,
    # so slightly more than this share can pass when several entities share a value.
    top_share: float = 0.5
    # Attempts to find an unused starting node that has at least one neighbor.
    max_start_attempts: int = 50

    def __post_init__(self) -> None:
        if not 1 <= self.min_hops <= self.max_hops:
            raise ValueError("hops must satisfy 1 <= min_hops <= max_hops")
        if not 0.0 < self.top_share <= 1.0:
            raise ValueError("top_share must be greater than 0 and at most 1")


class RandomWalker:
    def __init__(
        self,
        repository: GraphRepository,
        rng: random.Random | None = None,
        settings: WalkSettings | None = None,
    ) -> None:
        self._repository = repository
        self._rng = rng or random.Random()
        self._settings = settings or WalkSettings()

    def walk(self, exclude_start_ids: Collection[str] = ()) -> QuestionSeed:
        # Computed on every walk: cheap, and always matches the current import.
        thresholds = self._repository.fame_thresholds(self._settings.top_share)
        counts = {
            t: n for t, n in sorted(self._repository.type_counts(thresholds).items()) if n > 0
        }
        if not counts:
            raise NoQuestionSeedError("the knowledge graph is empty")

        for _ in range(self._settings.max_start_attempts):
            entity_type = self._rng.choice(list(counts))
            start = self._repository.node_of_type(
                entity_type, self._rng.randrange(counts[entity_type]), thresholds
            )
            if start is None or start.wikidata_id in exclude_start_ids:
                continue
            seed = self._walk_from(start, thresholds)
            if seed.edges:
                return self._with_fame_labels(seed)
        raise NoQuestionSeedError(
            f"no unused starting node with neighbors after {self._settings.max_start_attempts} "
            "attempts"
        )

    def _with_fame_labels(self, seed: QuestionSeed) -> QuestionSeed:
        levels = [(self._repository.fame_thresholds(share), label) for share, label in FAME_LEVELS]

        def labeled(node: GraphNode) -> GraphNode:
            for level_thresholds, label in levels:
                if node.sitelinks >= level_thresholds.get(node.entity_type, 0):
                    return replace(node, fame=label)
            return replace(node, fame=FAME_DEFAULT_LABEL)

        nodes = tuple(labeled(node) for node in seed.nodes)
        return QuestionSeed(start=nodes[0], nodes=nodes, edges=seed.edges)

    def _walk_from(self, start: GraphNode, thresholds: FameThresholds) -> QuestionSeed:
        hops = self._rng.randint(self._settings.min_hops, self._settings.max_hops)
        nodes = [start]
        edges: list[GraphEdge] = []
        visited = {start.wikidata_id}
        current = start
        for _ in range(hops):
            candidates = [
                n
                for n in self._repository.neighbors(current.wikidata_id, thresholds)
                if n.node.wikidata_id not in visited
            ]
            if not candidates:
                break
            # Sort before choosing so the result does not depend on database order.
            candidates.sort(key=lambda n: (n.node.wikidata_id, n.edge.relation))
            step = self._rng.choice(candidates)
            edges.append(step.edge)
            nodes.append(step.node)
            visited.add(step.node.wikidata_id)
            current = step.node
        return QuestionSeed(start=start, nodes=tuple(nodes), edges=tuple(edges))
