"""Graph data handed from the random walk to the question generator."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GraphNode:
    wikidata_id: str
    label: str
    entity_type: str
    description: str | None = None
    aliases: tuple[str, ...] = ()
    # Years and numeric facts as stored by the importer, e.g. {"population": 2100000}.
    facts: dict[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source: str
    relation: str
    target: str
    start_year: int | None = None
    end_year: int | None = None
    year: int | None = None


@dataclass(frozen=True)
class Neighbor:
    edge: GraphEdge
    node: GraphNode


@dataclass(frozen=True)
class QuestionSeed:
    """A small subgraph: the starting node and the path walked from it."""

    start: GraphNode
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
