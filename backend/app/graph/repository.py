"""Read access to the knowledge graph in Neo4j."""

from typing import Any, Protocol

from neo4j import Driver

from app.graph.model import GraphEdge, GraphNode, Neighbor

# Node properties written by the importer that are not facts about the entity.
_NON_FACT_PROPERTIES = frozenset(
    {"wikidata_id", "label", "description", "aliases", "sitelinks", "entity_type", "seq"}
)


class GraphRepository(Protocol):
    def fame_thresholds(self, top_share: float) -> dict[str, int]:
        """Per entity type, the sitelinks count that the most famous top_share reach."""
        ...

    def type_counts(self) -> dict[str, int]:
        """Number of entities per type."""
        ...

    def node_of_type(self, entity_type: str, index: int) -> GraphNode | None:
        """The index-th entity of a type, in a stable order."""
        ...

    def neighbors(self, wikidata_id: str) -> list[Neighbor]:
        """Connected entities, in either direction."""
        ...


class Neo4jGraphRepository:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def fame_thresholds(self, top_share: float) -> dict[str, int]:
        records, _, _ = self._driver.execute_query(
            "MATCH (n:Entity) "
            "RETURN n.entity_type AS type, percentileDisc(n.sitelinks, $percentile) AS threshold",
            percentile=max(0.0, 1.0 - top_share),
        )
        return {record["type"]: record["threshold"] for record in records}

    def type_counts(self) -> dict[str, int]:
        records, _, _ = self._driver.execute_query(
            "MATCH (n:Entity) RETURN n.entity_type AS type, count(*) AS count"
        )
        return {record["type"]: record["count"] for record in records}

    def node_of_type(self, entity_type: str, index: int) -> GraphNode | None:
        records, _, _ = self._driver.execute_query(
            "MATCH (n:Entity {entity_type: $type}) RETURN n ORDER BY n.seq SKIP $index LIMIT 1",
            type=entity_type,
            index=index,
        )
        return node_from_properties(dict(records[0]["n"])) if records else None

    def neighbors(self, wikidata_id: str) -> list[Neighbor]:
        records, _, _ = self._driver.execute_query(
            "MATCH (a:Entity {wikidata_id: $id})-[r]-(b:Entity) "
            "RETURN type(r) AS relation, startNode(r) = a AS outgoing, "
            "properties(r) AS props, b",
            id=wikidata_id,
        )
        neighbors = []
        for record in records:
            node = node_from_properties(dict(record["b"]))
            props: dict[str, Any] = record["props"]
            source, target = (
                (wikidata_id, node.wikidata_id)
                if record["outgoing"]
                else (node.wikidata_id, wikidata_id)
            )
            edge = GraphEdge(
                source=source,
                relation=record["relation"],
                target=target,
                start_year=props.get("start_year"),
                end_year=props.get("end_year"),
                year=props.get("year"),
            )
            neighbors.append(Neighbor(edge=edge, node=node))
        return neighbors


def node_from_properties(props: dict[str, Any]) -> GraphNode:
    return GraphNode(
        wikidata_id=props["wikidata_id"],
        label=props["label"],
        entity_type=props["entity_type"],
        description=props.get("description"),
        aliases=tuple(props.get("aliases") or ()),
        sitelinks=props.get("sitelinks", 0),
        facts={
            key: value
            for key, value in props.items()
            if key not in _NON_FACT_PROPERTIES and isinstance(value, int | float)
        },
    )
