"""Where the importer finds its files, and the Neo4j connection from the environment."""

import os
from pathlib import Path

# The repository root (offline/importer/settings.py -> two folders up). In the container
# that is /app, where config/ and data/ are mounted.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def neo4j_connection() -> tuple[str, str, str]:
    """URI, user and password of Neo4j. On the host, pass .env with
    `uv run --env-file .env ...`; the container gets the values from docker-compose.yml."""
    password = os.environ.get("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("Set NEO4J_PASSWORD (in .env).")
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    return uri, os.environ.get("NEO4J_USER", "neo4j"), password
