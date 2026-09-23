import math
import random
from itertools import pairwise

import pytest

from app.graph.model import GraphEdge, GraphNode, Neighbor
from app.graph.repository import FameThresholds, node_from_properties
from app.graph.walk import NoQuestionSeedError, RandomWalker, WalkSettings

ALL = WalkSettings(min_hops=1, max_hops=3, top_share=1.0)


class FakeRepository:
    """A line A - B - C - D, an isolated node X, and obscure nodes hanging off A and C.

    Sitelinks: the obscure cities O1 and O2 are the least famous of their type.
    """

    def __init__(self) -> None:
        self.sitelinks: dict[str, int] = {}
        self.nodes: dict[str, GraphNode] = {}
        for wikidata_id, label, entity_type, sitelinks in [
            ("A", "Alpha", "country", 300),
            ("B", "Beta", "city", 250),
            ("C", "Gamma", "river", 120),
            ("D", "Delta", "sea", 90),
            ("X", "Lonely", "island", 100),
            ("O1", "Obscure One", "city", 20),
            ("O2", "Obscure Two", "city", 30),
            ("B2", "Beta Two", "city", 200),
        ]:
            self.nodes[wikidata_id] = GraphNode(wikidata_id, label, entity_type)
            self.sitelinks[wikidata_id] = sitelinks
        self.edges = [
            ("A", "CAPITAL", "B"),
            ("C", "LOCATED_IN", "B"),
            ("C", "MOUTH", "D"),
            ("O1", "COUNTRY", "A"),
            ("O2", "LOCATED_IN", "C"),
            ("B2", "COUNTRY", "A"),
        ]

    def _passes(self, wikidata_id: str, thresholds: FameThresholds) -> bool:
        entity_type = self.nodes[wikidata_id].entity_type
        return self.sitelinks[wikidata_id] >= thresholds.get(entity_type, 0)

    def fame_thresholds(self, top_share: float) -> dict[str, int]:
        # Same meaning as Neo4j's percentileDisc(sitelinks, 1 - top_share).
        by_type: dict[str, list[int]] = {}
        for wikidata_id, node in self.nodes.items():
            by_type.setdefault(node.entity_type, []).append(self.sitelinks[wikidata_id])
        percentile = 1.0 - top_share
        result = {}
        for entity_type, values in by_type.items():
            values.sort()
            index = max(0, math.ceil(percentile * len(values)) - 1)
            result[entity_type] = values[index]
        return result

    def type_counts(self, thresholds: FameThresholds) -> dict[str, int]:
        counts: dict[str, int] = {}
        for wikidata_id, node in self.nodes.items():
            if self._passes(wikidata_id, thresholds):
                counts[node.entity_type] = counts.get(node.entity_type, 0) + 1
        return counts

    def node_of_type(
        self, entity_type: str, index: int, thresholds: FameThresholds
    ) -> GraphNode | None:
        matching = sorted(
            (
                node
                for wikidata_id, node in self.nodes.items()
                if node.entity_type == entity_type and self._passes(wikidata_id, thresholds)
            ),
            key=lambda n: n.wikidata_id,
        )
        return matching[index] if index < len(matching) else None

    def neighbors(self, wikidata_id: str, thresholds: FameThresholds) -> list[Neighbor]:
        result = []
        for source, relation, target in self.edges:
            if wikidata_id in (source, target):
                other = target if source == wikidata_id else source
                if self._passes(other, thresholds):
                    result.append(Neighbor(GraphEdge(source, relation, target), self.nodes[other]))
        return result


def test_walk_returns_connected_path_without_repeats() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(1), ALL)
    for _ in range(50):
        seed = walker.walk()
        ids = [node.wikidata_id for node in seed.nodes]
        assert seed.start == seed.nodes[0]
        assert len(set(ids)) == len(ids)
        assert 1 <= len(seed.edges) <= 3
        assert len(seed.nodes) == len(seed.edges) + 1
        for edge, (a, b) in zip(seed.edges, pairwise(ids), strict=True):
            assert {edge.source, edge.target} == {a, b}


def test_isolated_nodes_are_never_used() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(7), ALL)
    starts = {walker.walk().start.wikidata_id for _ in range(200)}
    assert "X" not in starts
    assert starts == {"A", "B", "B2", "C", "D", "O1", "O2"}


def test_top_share_keeps_obscure_entities_out_of_every_walk() -> None:
    # Cities have 250, 200, 30, 20 sitelinks. top_share 0.4 -> 60th percentile = 200,
    # so only B and B2 remain. (percentileDisc includes the boundary value.)
    walker = RandomWalker(FakeRepository(), random.Random(3), WalkSettings(top_share=0.4))
    for _ in range(200):
        ids = {node.wikidata_id for node in walker.walk().nodes}
        assert not ids & {"O1", "O2"}


def test_top_share_is_relative_per_type() -> None:
    # The only river (120 sitelinks) and sea (90) stay, although cities with more
    # sitelinks are excluded: fame is compared within a type.
    repository = FakeRepository()
    thresholds = repository.fame_thresholds(0.4)
    assert repository.type_counts(thresholds) == {
        "country": 1,
        "city": 2,
        "river": 1,
        "sea": 1,
        "island": 1,
    }


def test_default_walk_has_one_or_two_hops() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(11))
    hops = {len(walker.walk().edges) for _ in range(100)}
    assert hops == {1, 2}


def test_excluded_starts_are_skipped() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(3), ALL)
    for _ in range(30):
        start = walker.walk(exclude_start_ids={"A", "B", "B2", "C", "O1", "O2"}).start
        assert start.wikidata_id == "D"


def test_raises_when_no_start_is_left() -> None:
    settings = WalkSettings(top_share=1.0, max_start_attempts=20)
    walker = RandomWalker(FakeRepository(), random.Random(3), settings)
    with pytest.raises(NoQuestionSeedError):
        walker.walk(exclude_start_ids={"A", "B", "B2", "C", "D", "O1", "O2"})


def test_same_seed_gives_same_walk() -> None:
    first = RandomWalker(FakeRepository(), random.Random(42)).walk()
    second = RandomWalker(FakeRepository(), random.Random(42)).walk()
    assert first == second


def test_hop_count_respects_settings() -> None:
    settings = WalkSettings(min_hops=1, max_hops=1, top_share=1.0)
    walker = RandomWalker(FakeRepository(), random.Random(5), settings)
    assert all(len(walker.walk().edges) == 1 for _ in range(20))


@pytest.mark.parametrize(
    ("min_hops", "max_hops", "top_share"),
    [(0, 2, 0.5), (3, 2, 0.5), (1, 2, 0.0), (1, 2, 1.5)],
)
def test_invalid_settings_are_rejected(min_hops: int, max_hops: int, top_share: float) -> None:
    with pytest.raises(ValueError):
        WalkSettings(min_hops=min_hops, max_hops=max_hops, top_share=top_share)


def test_node_from_properties_separates_facts() -> None:
    node = node_from_properties(
        {
            "wikidata_id": "Q64",
            "label": "Berlin",
            "entity_type": "city",
            "aliases": ["Berlin"],
            "sitelinks": 300,
            "seq": 12,
            "population": 3677472,
            "population_year": 2023,
        }
    )
    assert node.facts == {"population": 3677472, "population_year": 2023}
    assert node.aliases == ("Berlin",)
    assert node.description is None
