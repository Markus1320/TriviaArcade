import random
from itertools import pairwise

import pytest

from app.graph.model import GraphEdge, GraphNode, Neighbor
from app.graph.repository import node_from_properties
from app.graph.walk import NoQuestionSeedError, RandomWalker, WalkSettings


class FakeRepository:
    """A tiny graph: A - B - C - D in a line, plus an isolated node X."""

    def __init__(self) -> None:
        self.nodes = {
            "A": GraphNode("A", "Alpha", "country"),
            "B": GraphNode("B", "Beta", "city"),
            "C": GraphNode("C", "Gamma", "river"),
            "D": GraphNode("D", "Delta", "sea"),
            "X": GraphNode("X", "Lonely", "island"),
        }
        self.edges = [("A", "CAPITAL", "B"), ("C", "LOCATED_IN", "B"), ("C", "MOUTH", "D")]

    def type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.nodes.values():
            counts[node.entity_type] = counts.get(node.entity_type, 0) + 1
        return counts

    def node_of_type(self, entity_type: str, index: int) -> GraphNode | None:
        matching = sorted(
            (n for n in self.nodes.values() if n.entity_type == entity_type),
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
    walker = RandomWalker(FakeRepository(), random.Random(1))
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
    walker = RandomWalker(FakeRepository(), random.Random(7))
    starts = {walker.walk().start.wikidata_id for _ in range(100)}
    assert "X" not in starts
    assert starts == {"A", "B", "C", "D"}


def test_excluded_starts_are_skipped() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(3))
    for _ in range(30):
        assert walker.walk(exclude_start_ids={"A", "B", "C"}).start.wikidata_id == "D"


def test_raises_when_no_start_is_left() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(3), WalkSettings(max_start_attempts=20))
    with pytest.raises(NoQuestionSeedError):
        walker.walk(exclude_start_ids={"A", "B", "C", "D"})


def test_same_seed_gives_same_walk() -> None:
    first = RandomWalker(FakeRepository(), random.Random(42)).walk()
    second = RandomWalker(FakeRepository(), random.Random(42)).walk()
    assert first == second


def test_hop_count_respects_settings() -> None:
    walker = RandomWalker(FakeRepository(), random.Random(5), WalkSettings(min_hops=1, max_hops=1))
    assert all(len(walker.walk().edges) == 1 for _ in range(20))


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
