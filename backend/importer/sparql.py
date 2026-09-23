"""Client for the Wikidata SPARQL endpoint with rate limiting, retries and a raw cache."""

import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx2

from importer.config import WikidataConfig
from importer.parsing import Row
from importer.queries import query_kind

logger = logging.getLogger(__name__)

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_BASE_BACKOFF_SECONDS = 5.0


class SparqlError(RuntimeError):
    pass


class SparqlClient:
    """Runs SELECT queries and caches the simplified rows in cache_dir.

    Cached responses are reused on later runs unless refresh is set, so repeated imports
    do not put load on the public endpoint.
    """

    def __init__(
        self,
        config: WikidataConfig,
        cache_dir: Path,
        *,
        refresh: bool = False,
        http: httpx2.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._cache_dir = cache_dir
        self._refresh = refresh
        self._http = http or httpx2.Client(
            headers={
                "User-Agent": config.user_agent,
                "Accept": "application/sparql-results+json",
            },
            timeout=config.timeout_seconds,
        )
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self.requests_sent = 0
        self.cache_hits = 0

    def close(self) -> None:
        self._http.close()

    def select(self, query: str) -> list[Row]:
        cache_file = self._cache_file(query)
        if not self._refresh and cache_file.exists():
            self.cache_hits += 1
            cached: dict[str, Any] = json.loads(cache_file.read_text(encoding="utf-8"))
            rows: list[Row] = cached["rows"]
            return rows

        rows = self._fetch(query)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(
            json.dumps({"query": query, "rows": rows}, ensure_ascii=False), encoding="utf-8"
        )
        return rows

    def _cache_file(self, query: str) -> Path:
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:20]
        return self._cache_dir / f"{query_kind(query)}-{digest}.json"

    def _fetch(self, query: str) -> list[Row]:
        for attempt in range(self._config.max_retries + 1):
            self._respect_interval()
            wait: float | None = None
            try:
                response = self._http.post(self._config.endpoint, data={"query": query})
                self.requests_sent += 1
                if response.status_code in _RETRY_STATUS:
                    wait = _retry_after(response)
                    reason = f"HTTP {response.status_code}"
                else:
                    response.raise_for_status()
                    return _simplify(response.json())
            except httpx2.HTTPStatusError as error:
                raise SparqlError(
                    f"{query_kind(query)} query failed: {error}\n{error.response.text[:500]}"
                ) from error
            except (httpx2.TransportError, json.JSONDecodeError) as error:
                reason = type(error).__name__

            if attempt == self._config.max_retries:
                raise SparqlError(f"{query_kind(query)} query failed after retries: {reason}")
            backoff = max(wait or 0.0, _BASE_BACKOFF_SECONDS * 2**attempt)
            logger.warning("%s query: %s, retrying in %.0f s", query_kind(query), reason, backoff)
            self._sleep(backoff)
        raise AssertionError("unreachable")

    def _respect_interval(self) -> None:
        if self._last_request is not None:
            elapsed = self._clock() - self._last_request
            remaining = self._config.min_interval_seconds - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self._last_request = self._clock()


def _retry_after(response: httpx2.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _simplify(payload: dict[str, Any]) -> list[Row]:
    """Reduce SPARQL JSON bindings to {variable: value} dictionaries."""
    bindings: list[dict[str, dict[str, str]]] = payload["results"]["bindings"]
    return [{name: cell["value"] for name, cell in binding.items()} for binding in bindings]
