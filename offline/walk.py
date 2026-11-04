"""The random walk through the knowledge graph in Neo4j: a few connected facts for one
question, and those facts as text for the writer.

1. Pick an entity type, every type equally likely, then a random entity of that type.
   Every type is an equal slice of the question starts, however many entities it has.
   Starts already used by the pool are skipped.
2. Walk min_hops to max_hops hops to entities not visited yet. Each hop picks a neighbour
   with weight 1 / degree ** hub_penalty: without it, walks end at a few hubs (the United
   States has hundreds of relations) and the writer then asks about the hub.

Every entity in the graph can take part. What is too obscure is kept out at import time
by the fame thresholds in config/import.yaml.
"""

import random
from collections.abc import Collection
from dataclasses import dataclass, field

from neo4j import Driver

# Attempts to find an unused start that has at least one neighbour.
MAX_START_ATTEMPTS = 50
# Aliases shown per entity in the facts text.
MAX_ALIASES = 6
# Node properties written by the importer that are not facts about the entity.
NOT_FACTS = {"wikidata_id", "label", "description", "aliases", "sitelinks", "entity_type", "seq"}


@dataclass(frozen=True)
class Node:
    wikidata_id: str
    label: str
    entity_type: str
    description: str | None = None
    aliases: tuple[str, ...] = ()
    # Years and numbers as stored by the importer, e.g. {"population": 2100000}.
    facts: dict[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    start_year: int | None = None
    end_year: int | None = None
    year: int | None = None


@dataclass(frozen=True)
class Walk:
    """The start entity, every entity visited (the start first) and the hops between them."""

    start: Node
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


class NoWalkError(Exception):
    """No unused start with neighbours was found."""


def random_walk(
    driver: Driver,
    rng: random.Random,
    used_starts: Collection[str] = (),
    min_hops: int = 1,
    max_hops: int = 2,
    hub_penalty: float = 0.5,
    start_types: Collection[str] = (),
) -> Walk:
    """start_types: only start from these entity types; empty means all."""
    counts = {
        entity_type: count
        for entity_type, count in sorted(type_counts(driver).items())
        if count > 0 and (not start_types or entity_type in start_types)
    }
    if not counts:
        raise NoWalkError("the knowledge graph is empty")
    for _ in range(MAX_START_ATTEMPTS):
        entity_type = rng.choice(list(counts))
        start = node_of_type(driver, entity_type, rng.randrange(counts[entity_type]))
        if start is None or start.wikidata_id in used_starts:
            continue
        walk = walk_from(driver, rng, start, rng.randint(min_hops, max_hops), hub_penalty)
        if walk.edges:
            return walk
    raise NoWalkError(f"no unused start with neighbours after {MAX_START_ATTEMPTS} attempts")


def walk_from(
    driver: Driver, rng: random.Random, start: Node, hops: int, hub_penalty: float
) -> Walk:
    nodes = [start]
    edges: list[Edge] = []
    current = start
    for _ in range(hops):
        visited = {node.wikidata_id for node in nodes}
        # Every neighbouring entity counts once, however many relations lead to it (a film
        # made in and set in the United States). Sorted, so the result does not depend on
        # the order Neo4j returns them in.
        by_node: dict[str, list[tuple[Edge, Node, int]]] = {}
        for edge, node, degree in sorted(
            neighbours(driver, current.wikidata_id),
            key=lambda found: (found[1].wikidata_id, found[0].relation),
        ):
            if node.wikidata_id not in visited:
                by_node.setdefault(node.wikidata_id, []).append((edge, node, degree))
        if not by_node:
            break  # a dead end ends the walk early
        choices = list(by_node.values())
        weights = [max(choice[0][2], 1) ** -hub_penalty for choice in choices]
        edge, node, _ = rng.choice(rng.choices(choices, weights)[0])
        edges.append(edge)
        nodes.append(node)
        current = node
    return Walk(start=start, nodes=tuple(nodes), edges=tuple(edges))


# --- Reading the graph ---


def type_counts(driver: Driver) -> dict[str, int]:
    records, _, _ = driver.execute_query(
        "MATCH (n:Entity) RETURN n.entity_type AS type, count(*) AS count"
    )
    return {record["type"]: record["count"] for record in records}


def node_of_type(driver: Driver, entity_type: str, index: int) -> Node | None:
    """The index-th entity of a type, in a stable order."""
    records, _, _ = driver.execute_query(
        "MATCH (n:Entity {entity_type: $type}) RETURN n ORDER BY n.seq SKIP $index LIMIT 1",
        type=entity_type,
        index=index,
    )
    return node_from(dict(records[0]["n"])) if records else None


def neighbours(driver: Driver, wikidata_id: str) -> list[tuple[Edge, Node, int]]:
    """Connected entities in either direction, each with the edge and its number of
    relations (high for hubs such as countries)."""
    records, _, _ = driver.execute_query(
        "MATCH (a:Entity {wikidata_id: $id})-[r]-(b:Entity) "
        "RETURN type(r) AS relation, startNode(r) = a AS outgoing, "
        "properties(r) AS props, b, COUNT { (b)--() } AS degree",
        id=wikidata_id,
    )
    found = []
    for record in records:
        node = node_from(dict(record["b"]))
        props = record["props"]
        if record["outgoing"]:
            source, target = wikidata_id, node.wikidata_id
        else:
            source, target = node.wikidata_id, wikidata_id
        edge = Edge(
            source=source,
            relation=record["relation"],
            target=target,
            start_year=props.get("start_year"),
            end_year=props.get("end_year"),
            year=props.get("year"),
        )
        found.append((edge, node, record["degree"]))
    return found


def node_from(props: dict) -> Node:
    return Node(
        wikidata_id=props["wikidata_id"],
        label=props["label"],
        entity_type=props["entity_type"],
        description=props.get("description"),
        aliases=tuple(props.get("aliases") or ()),
        facts={
            key: value
            for key, value in props.items()
            if key not in NOT_FACTS and isinstance(value, int | float)
        },
    )


# --- The walk as text for the writer ---

# How stored facts are shown. Unknown keys are shown as "key: value".
QUANTITY_FORMATS = {
    "population": "population {value:,.0f}",
    "area_km2": "area {value:,.0f} km²",
    "length_km": "length {value:,.0f} km",
    "elevation_m": "elevation {value:,.0f} m",
}
YEAR_LABELS = {
    "year": "year",
    "start_year": "start",
    "end_year": "end",
    "inception_year": "founded",
    "publication_year": "released",
    "dissolved_year": "dissolved",
    "birth_year": "born",
    "death_year": "died",
}


def facts_text(walk: Walk) -> str:
    """For example:

    Entities:
    - Seoul (city; capital of South Korea): population 9,668,465 (as of 2020). Also known as: ...

    Relations (walked in this order):
    - 1988 Summer Olympics -- located in --> Seoul
    """
    labels = {node.wikidata_id: node.label for node in walk.nodes}
    lines = ["Entities:"]
    lines += [f"- {describe_node(node)}" for node in walk.nodes]
    lines += ["", "Relations (walked in this order):"]
    lines += [f"- {describe_edge(edge, labels)}" for edge in walk.edges]
    return "\n".join(lines)


def describe_node(node: Node) -> str:
    text = f"{node.label} ({node.entity_type.replace('_', ' ')}"
    if node.description:
        text += f"; {node.description}"
    text += ")"
    facts = describe_facts(node.facts)
    if facts:
        text += f": {facts}"
    if node.aliases:
        text += f". Also known as: {', '.join(node.aliases[:MAX_ALIASES])}"
    return text


def describe_facts(facts: dict[str, int | float]) -> str:
    parts = []
    for key, value in sorted(facts.items()):
        if key in QUANTITY_FORMATS:
            text = QUANTITY_FORMATS[key].format(value=value)
            reference_year = facts.get(f"{key}_year")
            if reference_year is not None:
                text += f" (as of {format_year(int(reference_year))})"
            parts.append(text)
        elif key.endswith("_year") and key.removesuffix("_year") in QUANTITY_FORMATS:
            continue  # the reference year, shown together with its value
        elif key in YEAR_LABELS:
            parts.append(f"{YEAR_LABELS[key]} {format_year(int(value))}")
        else:
            parts.append(f"{key.replace('_', ' ')}: {value}")
    return "; ".join(parts)


def describe_edge(edge: Edge, labels: dict[str, str]) -> str:
    relation = edge.relation.lower().replace("_", " ")
    text = f"{labels[edge.source]} -- {relation} --> {labels[edge.target]}"
    period = []
    if edge.year is not None:
        period.append(f"in {format_year(edge.year)}")
    if edge.start_year is not None:
        period.append(f"from {format_year(edge.start_year)}")
    if edge.end_year is not None:
        period.append(f"until {format_year(edge.end_year)}")
    if period:
        text += f" ({' '.join(period)})"
    return text


def format_year(year: int) -> str:
    return f"{-year} BC" if year < 0 else str(year)
