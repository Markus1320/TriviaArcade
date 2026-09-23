from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.health import Check, get_neo4j_check, get_postgres_check
from app.main import app


def _ok() -> None:
    return None


def _fail() -> None:
    raise ConnectionError("unreachable")


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _override(postgres: Check, neo4j: Check) -> None:
    app.dependency_overrides[get_postgres_check] = lambda: postgres
    app.dependency_overrides[get_neo4j_check] = lambda: neo4j


def test_health_ok_when_both_databases_answer(client: TestClient) -> None:
    _override(postgres=_ok, neo4j=_ok)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "postgres": "ok", "neo4j": "ok"}


@pytest.mark.parametrize(
    ("postgres", "neo4j", "expected"),
    [
        (_fail, _ok, {"status": "error", "postgres": "error", "neo4j": "ok"}),
        (_ok, _fail, {"status": "error", "postgres": "ok", "neo4j": "error"}),
        (_fail, _fail, {"status": "error", "postgres": "error", "neo4j": "error"}),
    ],
)
def test_health_reports_failing_database(
    client: TestClient, postgres: Check, neo4j: Check, expected: dict[str, str]
) -> None:
    _override(postgres=postgres, neo4j=neo4j)
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json() == expected
