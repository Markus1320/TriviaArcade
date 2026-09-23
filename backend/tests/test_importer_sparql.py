"""SparqlClient against a mocked HTTP transport; no network access."""

from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest

from importer.config import WikidataConfig
from importer.sparql import SparqlClient, SparqlError

QUERY = "# kind: test\nSELECT ?x WHERE { }"
PAYLOAD = {"results": {"bindings": [{"x": {"type": "literal", "value": "1"}}]}}

Handler = Callable[[httpx2.Request], httpx2.Response]


def make_client(
    handler: Handler, cache_dir: Path, sleeps: list[float], *, refresh: bool = False
) -> SparqlClient:
    config = WikidataConfig(
        endpoint="https://example.invalid/sparql",
        user_agent="TriviaArcade tests (https://example.invalid)",
        min_interval_seconds=0,
        timeout_seconds=5,
        max_retries=2,
        batch_size=10,
        label_batch_size=10,
    )
    http = httpx2.Client(
        transport=httpx2.MockTransport(handler), headers={"User-Agent": config.user_agent}
    )
    return SparqlClient(config, cache_dir, http=http, sleep=sleeps.append, refresh=refresh)


def test_rows_are_simplified_and_cached(tmp_path: Path) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json=PAYLOAD)

    client = make_client(handler, tmp_path, [])
    assert client.select(QUERY) == [{"x": "1"}]
    assert client.select(QUERY) == [{"x": "1"}]
    assert len(calls) == 1
    assert calls[0].headers["User-Agent"].startswith("TriviaArcade")
    assert [path.name.split("-")[0] for path in tmp_path.iterdir()] == ["test"]


def test_refresh_ignores_cache(tmp_path: Path) -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json=PAYLOAD)

    make_client(handler, tmp_path, []).select(QUERY)
    make_client(handler, tmp_path, [], refresh=True).select(QUERY)
    assert len(calls) == 2


def test_retries_rate_limit_with_retry_after(tmp_path: Path) -> None:
    responses = [
        httpx2.Response(429, headers={"Retry-After": "30"}),
        httpx2.Response(200, json=PAYLOAD),
    ]
    sleeps: list[float] = []
    client = make_client(lambda _: responses.pop(0), tmp_path, sleeps)
    assert client.select(QUERY) == [{"x": "1"}]
    assert sleeps == [30.0]


def test_gives_up_after_max_retries(tmp_path: Path) -> None:
    sleeps: list[float] = []
    client = make_client(lambda _: httpx2.Response(503), tmp_path, sleeps)
    with pytest.raises(SparqlError, match="after retries"):
        client.select(QUERY)
    assert sleeps == [5.0, 10.0]
    assert not list(tmp_path.iterdir())


def test_client_errors_are_not_retried(tmp_path: Path) -> None:
    sleeps: list[float] = []
    client = make_client(lambda _: httpx2.Response(400, text="bad query"), tmp_path, sleeps)
    with pytest.raises(SparqlError, match="bad query"):
        client.select(QUERY)
    assert sleeps == []
