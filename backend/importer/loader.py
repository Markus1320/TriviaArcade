"""Writes an imported graph into Neo4j, replacing the previous graph."""

import logging
from collections import defaultdict
from typing import Any, LiteralString

from neo4j import Driver, ManagedTransaction, Session

from importer.model import ImportedGraph, Node, Relation

logger = logging.getLogger(__name__)

_WRITE_BATCH = 1000

_SCHEMA: list[LiteralString] = [
    "CREATE CONSTRAINT entity_wikidata_id IF NOT EXISTS "
    "FOR (n:Entity) REQUIRE n.wikidata_id IS UNIQUE",
    "CREATE CONSTRAINT entity_seq IF NOT EXISTS FOR (n:Entity) REQUIRE n.seq IS UNIQUE",
    "CREATE INDEX entity_type IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)",
    "CREATE INDEX entity_sitelinks IF NOT EXISTS FOR (n:Entity) ON (n.sitelinks)",
]


def type_label(entity_type: str) -> str:
    """historical_state -> HistoricalState, used as a second node label for browsing."""
    label = "".join(part.capitalize() for part in entity_type.split("_"))
    if not label.isalpha():
        raise ValueError(f"invalid entity type for a label: {entity_type!r}")
    return label


def node_record(node: Node, seq: int) -> dict[str, Any]:
    return {
        "wikidata_id": node.wikidata_id,
        "label": node.label,
        "description": node.description,
        "aliases": node.aliases,
        "sitelinks": node.sitelinks,
        "entity_type": node.entity_type,
        # Dense numbering 0..n-1, so random selection can pick a number in code.
        "seq": seq,
        **node.facts,
    }


def relation_properties(relation: Relation) -> dict[str, Any]:
    properties: dict[str, Any] = {"property": relation.property}
    for key in ("start_year", "end_year", "year"):
        value = getattr(relation, key)
        if value is not None:
            properties[key] = value
    return properties


def load_graph(driver: Driver, graph: ImportedGraph) -> None:
    with driver.session() as session:
        logger.info("Clearing previous graph")
        session.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS")
        for statement in _SCHEMA:
            session.run(statement)
        _write_nodes(session, graph.nodes)
        _write_relations(session, graph.relations)
        session.run(
            "CREATE (:ImportMeta {imported_at: datetime(), nodes: $nodes, relations: $relations})",
            nodes=len(graph.nodes),
            relations=len(graph.relations),
        )
    logger.info("Loaded %d nodes and %d relations", len(graph.nodes), len(graph.relations))


def _write_nodes(session: Session, nodes: list[Node]) -> None:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for seq, node in enumerate(nodes):
        by_type[node.entity_type].append(node_record(node, seq))
    for entity_type, records in sorted(by_type.items()):
        # Labels cannot be query parameters; type_label only returns letters.
        query: LiteralString = (
            f"UNWIND $rows AS row CREATE (n:Entity:{type_label(entity_type)}) SET n = row"
        )
        _write_batches(session, query, records)


def _write_relations(session: Session, relations: list[Relation]) -> None:
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relation in relations:
        by_name[relation.name].append(
            {
                "source": relation.source,
                "target": relation.target,
                "props": relation_properties(relation),
            }
        )
    for name, records in sorted(by_name.items()):
        # Relationship types cannot be parameters; the config restricts names to A-Z and _.
        if not name.replace("_", "").isalpha():
            raise ValueError(f"invalid relation name: {name!r}")
        query: LiteralString = (
            "UNWIND $rows AS row "
            "MATCH (a:Entity {wikidata_id: row.source}) "
            "MATCH (b:Entity {wikidata_id: row.target}) "
            f"CREATE (a)-[r:{name}]->(b) SET r = row.props"
        )
        _write_batches(session, query, records)


def _write_batches(session: Session, query: LiteralString, records: list[dict[str, Any]]) -> None:
    def write(tx: ManagedTransaction, rows: list[dict[str, Any]]) -> None:
        tx.run(query, rows=rows)

    for start in range(0, len(records), _WRITE_BATCH):
        session.execute_write(write, records[start : start + _WRITE_BATCH])
