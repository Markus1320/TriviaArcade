"""Neo4j driver for the knowledge graph."""

from functools import lru_cache

from neo4j import Driver, GraphDatabase

from app.config import get_settings


@lru_cache
def get_driver() -> Driver:
    settings = get_settings()
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        connection_timeout=settings.health_timeout_seconds,
    )


def ping_neo4j(driver: Driver) -> None:
    """Raise if Neo4j cannot be reached."""
    driver.verify_connectivity()
