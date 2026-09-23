"""Command line entry point: python -m importer."""

import argparse
import logging
import sys
from pathlib import Path

from neo4j import GraphDatabase

from importer.build import GraphBuilder
from importer.config import load_config
from importer.loader import load_graph
from importer.model import ImportedGraph
from importer.settings import PROJECT_ROOT, ImporterSettings
from importer.sparql import SparqlClient, SparqlError

logger = logging.getLogger("importer")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m importer", description="Import Wikidata facts into Neo4j."
    )
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "import.yaml")
    parser.add_argument("--cache-dir", type=Path, default=PROJECT_ROOT / "data" / "raw")
    parser.add_argument(
        "--refresh", action="store_true", help="ignore cached responses and query again"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="build the graph and print stats, skip Neo4j"
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)

    config = load_config(args.config)
    client = SparqlClient(config.wikidata, args.cache_dir, refresh=args.refresh)
    try:
        graph = GraphBuilder(config, client.select).build()
    except SparqlError as error:
        logger.error("%s", error)
        return 1
    finally:
        client.close()
    logger.info(
        "Wikidata requests: %d sent, %d from cache", client.requests_sent, client.cache_hits
    )
    _log_summary(graph)

    if args.dry_run:
        return 0
    settings = ImporterSettings()
    with GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        # Skip informational notices such as "constraint already exists".
        notifications_min_severity="WARNING",
    ) as driver:
        load_graph(driver, graph)
    return 0


def _log_summary(graph: ImportedGraph) -> None:
    logger.info("Nodes by type (%d total):", len(graph.nodes))
    for name, count in graph.type_counts().most_common():
        logger.info("  %-26s %6d", name, count)
    logger.info("Relations by type (%d total):", len(graph.relations))
    for name, count in graph.relation_counts().most_common():
        logger.info("  %-26s %6d", name, count)
    with_facts = sum(1 for node in graph.nodes if node.facts)
    logger.info("Nodes with years or numeric facts: %d", with_facts)


if __name__ == "__main__":
    sys.exit(main())
