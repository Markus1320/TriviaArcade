import math
import random
from itertools import pairwise

import pytest

from app.graph.model import GraphEdge, GraphNode, Neighbor
from app.graph.repository import node_from_properties
from app.graph.walk import (
    FAME_DEFAULT_LABEL,
    NoQuestionSeedError,
    RandomWalker,
    WalkSettings,
)

LONG = WalkSettings(min_hops=1, max_hops=3)


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
            self.nodes[wikidata_id] = GraphNode(
                wikidata_id, label, entity_type, sitelinks=sitelinks
            )
            self.sitelinks[wikidata_id] = sitelinks
        self.edges = [
            ("A", "CAPITAL", "B"),
            ("C", "LOCATED_IN", "B"),
            ("C", "MOUTH", "D"),
            ("O1", "COUNTRY", "A"),
            ("O2", "LOCATED_IN", "C"),
            ("B2", "COUNTRY", "A"),
        ]

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

    def type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.nodes.values():
            counts[node.entity_type] = counts.get(node.entity_type, 0) + 1
        return counts

    def node_of_type(self, entity_type: str, index: int) -> GraphNode | None:
        matching = sorted(
            (node for node in self.nodes.values() if node.entity_type == entity_type),
            key=lambda n: n.wikidata_id,
        )
        return matching[index] if index < len(matching) else None

    def neighbors(self, wikidata_id: str) -> list[Neighbor]:
        result = []
        for source, relation, target in self.edges:
            if wikidata_id in (source, target):
                other = target if source == wikidata_id else source
                result.append(Neighbor(GraphEdge(source, relation, target), self.nodes[other]))
        return result


def test_walk_returns_connected_path_without_repeats() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(1), LONG)
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
    walker = RandomWalker(FakeRepository(), random.Random(7), LONG)
    starts = {walker.walk().start.wikidata_id for _ in range(200)}
    assert "X" not in starts
    assert starts == {"A", "B", "B2", "C", "D", "O1", "O2"}


def test_every_type_is_an_equal_slice_of_the_starts() -> None:
    # Four types have usable starts (the island is isolated and retried): the single
    # country starts about as many walks as the four cities together.
    walker = RandomWalker(FakeRepository(), random.Random(5), LONG)
    starts = [walker.walk().start for _ in range(4000)]
    by_type = {t: sum(1 for s in starts if s.entity_type == t) for t in ("country", "city")}
    assert 0.2 < by_type["country"] / len(starts) < 0.3
    assert 0.2 < by_type["city"] / len(starts) < 0.3
    # Within a type every entity is equally likely, whatever its fame.
    cities = [s.wikidata_id for s in starts if s.entity_type == "city"]
    for wikidata_id in ("B", "B2", "O1", "O2"):
        assert 0.2 < cities.count(wikidata_id) / len(cities) < 0.3


def test_nodes_get_fame_labels_relative_to_their_type() -> None:
    # Cities: 250 (top 10%), 200 (top 30%), 30 and 20 (below).
    walker = RandomWalker(FakeRepository(), random.Random(2), LONG)
    labels: dict[str, str | None] = {}
    for _ in range(200):
        for node in walker.walk().nodes:
            labels[node.wikidata_id] = node.fame
    assert labels["B"] == "world famous"
    assert labels["B2"] == "well known"
    assert labels["O1"] == FAME_DEFAULT_LABEL
    # The only river is the most famous of its kind.
    assert labels["C"] == "world famous"


def test_default_walk_has_one_or_two_hops() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(11))
    hops = {len(walker.walk().edges) for _ in range(100)}
    assert hops == {1, 2}


def test_excluded_starts_are_skipped() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(3), LONG)
    for _ in range(30):
        start = walker.walk(exclude_start_ids={"A", "B", "B2", "C", "O1", "O2"}).start
        assert start.wikidata_id == "D"


def test_raises_when_no_start_is_left() -> None:
    settings = WalkSettings(max_start_attempts=20)
    walker = RandomWalker(FakeRepository(), random.Random(3), settings)
    with pytest.raises(NoQuestionSeedError):
        walker.walk(exclude_start_ids={"A", "B", "B2", "C", "D", "O1", "O2"})


def test_same_seed_gives_same_walk() -> None:
    first = RandomWalker(FakeRepository(), random.Random(42)).walk()
    second = RandomWalker(FakeRepository(), random.Random(42)).walk()
    assert first == second


def test_hop_count_respects_settings() -> None:
    settings = WalkSettings(min_hops=1, max_hops=1)
    walker = RandomWalker(FakeRepository(), random.Random(5), settings)
    assert all(len(walker.walk().edges) == 1 for _ in range(20))


@pytest.mark.parametrize(
    ("min_hops", "max_hops"),
    [(0, 2), (3, 2)],
)
def test_invalid_settings_are_rejected(min_hops: int, max_hops: int) -> None:
    with pytest.raises(ValueError):
        WalkSettings(min_hops=min_hops, max_hops=max_hops)


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
