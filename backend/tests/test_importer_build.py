"""GraphBuilder with canned SPARQL results; no network access."""

import re
from typing import Any

import pytest

from importer.build import GraphBuilder
from importer.config import ImportConfig
from importer.model import ImportedGraph, Relation
from importer.parsing import ENTITY_PREFIX, PREFERRED_RANK, Row
from importer.queries import query_kind

E = ENTITY_PREFIX
NORMAL_RANK = "http://wikiba.se/ontology#NormalRank"


def make_config(**overrides: Any) -> ImportConfig:
    data: dict[str, Any] = {
        "wikidata": {
            "endpoint": "https://example.invalid/sparql",
            "user_agent": "TriviaArcade tests",
            "min_interval_seconds": 0,
            "timeout_seconds": 5,
            "max_retries": 0,
            "batch_size": 50,
            "label_batch_size": 50,
        },
        "languages": ["en", "de"],
        "label_fallback_languages": ["mul"],
        "fame_threshold": 50,
        "related_fame_threshold": 100,
        "numeric_fame_threshold": 200,
        "entity_types": {
            "country": {"classes": ["Q6256"]},
            "city": {"classes": ["Q515"], "fame_threshold": 100, "max_entities": 1},
        },
        "related_types": {"person": {"classes": ["Q5"]}},
        "relations": [
            {
                "property": "P36",
                "name": "CAPITAL",
                "target_fame_threshold": 0,
                "fallback_target_type": "city",
                "best_rank_only": True,
            },
            {"property": "P35", "name": "HEAD_OF_STATE"},
            {"property": "P19", "name": "PLACE_OF_BIRTH", "from_related": True},
        ],
        "numeric_properties": [
            {"property": "P1082", "name": "population", "unit": None, "with_year": True}
        ],
        "date_properties": [
            {"property": "P571", "name": "inception_year", "tier": "numeric"},
            {"property": "P585", "name": "year", "tier": "base"},
        ],
    }
    data.update(overrides)
    return ImportConfig.model_validate(data)


def statement(s: str, pid: str, o: str, osl: int, **extra: str) -> Row:
    return {"s": E + s, "pid": pid, "o": E + o, "osl": str(osl), **extra}


def label(s: str, kind: str, lang: str, text: str) -> Row:
    return {"s": E + s, "kind": kind, "lang": lang, "text": text}


def date(s: str, pid: str, time: str, precision: int, rank: str = NORMAL_RANK) -> Row:
    return {"s": E + s, "pid": pid, "time": time, "precision": str(precision), "rank": rank}


def quantity(s: str, amount: str, pit: str, rank: str = NORMAL_RANK) -> Row:
    return {
        "s": E + s,
        "pid": "P1082",
        "amount": amount,
        "unit": E + "Q199",
        "pit": pit,
        "rank": rank,
    }


class FakeWikidata:
    """Routes queries by their kind and records them for assertions."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def select(self, query: str) -> list[Row]:
        self.queries.append(query)
        rows = self._rows(query)
        # Like the real endpoint, only answer for subjects listed in the query.
        requested = set(re.findall(r"wd:(Q\d+)", query))
        return [row for row in rows if "s" not in row or row["s"][len(E) :] in requested]

    def _rows(self, query: str) -> list[Row]:
        kind = query_kind(query)
        if kind == "entities":
            if "wd:Q6256" in query:
                return [
                    {"item": E + "Q1", "sitelinks": "300"},
                    {"item": E + "Q2", "sitelinks": "60"},
                ]
            return [
                {"item": E + "Q10", "sitelinks": "500"},
                {"item": E + "Q11", "sitelinks": "150"},
            ]
        if kind == "statements" and '"P36"' in query:
            return [
                statement("Q1", "P36", "Q10", 500, rank=PREFERRED_RANK),
                statement("Q1", "P36", "Q12", 5, rank=NORMAL_RANK),  # former capital
                statement("Q2", "P36", "Q12", 5),  # only capital, kept; target threshold 0
                statement("Q1", "P35", "Q20", 150, start="1990-01-01T00:00:00Z"),
                statement("Q1", "P35", "Q21", 20),  # below related threshold
                statement("Q2", "P35", "Q22", 500),  # cannot be classified
            ]
        if kind == "statements":
            return [
                statement("Q20", "P19", "Q10", 500),
                statement("Q20", "P19", "Q99", 900),  # not in graph, never added
            ]
        if kind == "classes":
            return [
                {"s": E + "Q20", "class": E + "Q5"},
                {"s": E + "Q22", "class": E + "Q999"},
            ]
        if kind == "labels":
            return [
                label("Q1", "label", "en", "Freedonia"),
                label("Q1", "label", "de", "Freedonien"),
                label("Q1", "alias", "en", "freedonia"),
                label("Q1", "alias", "en", "FD"),
                label("Q1", "description", "en", "fictional country"),
                label("Q2", "label", "de", "Nur Deutsch"),  # no English label
                label("Q10", "label", "en", "Capital City"),
                label("Q11", "label", "en", "Second City"),
                label("Q12", "label", "mul", "Smallcap"),  # only a "mul" label
                label("Q20", "label", "en", "Rufus T. Firefly"),
            ]
        if kind == "dates":
            return [
                date("Q1", "P571", "1800-01-01T00:00:00Z", 9),
                date("Q1", "P571", "1790-01-01T00:00:00Z", 9, PREFERRED_RANK),
                date("Q10", "P571", "-0043-01-01T00:00:00Z", 9),
                date("Q20", "P571", "1850-01-01T00:00:00Z", 9),  # numeric tier, too obscure
                date("Q20", "P585", "1900-01-01T00:00:00Z", 9),
                date("Q12", "P585", "1500-01-01T00:00:00Z", 7),  # century precision
            ]
        if kind == "quantities":
            return [
                quantity("Q1", "100", "2000-01-01T00:00:00Z"),
                quantity("Q1", "120", "2010-01-01T00:00:00Z"),
                quantity("Q10", "5", "1990-01-01T00:00:00Z", PREFERRED_RANK),
                quantity("Q10", "7", "2020-01-01T00:00:00Z"),
            ]
        raise AssertionError(f"unexpected query kind {kind}")


@pytest.fixture
def built() -> tuple[ImportedGraph, FakeWikidata]:
    fake = FakeWikidata()
    graph = GraphBuilder(make_config(), fake.select).build()
    return graph, fake


def test_nodes_respect_thresholds_caps_and_classification(
    built: tuple[ImportedGraph, FakeWikidata],
) -> None:
    graph, _ = built
    types = {node.wikidata_id: node.entity_type for node in graph.nodes}
    # Q2: no English label. Q11: cut by max_entities. Q21: below related threshold.
    # Q22: unclassifiable without fallback. Q99: only reachable from a reached entity.
    assert types == {"Q1": "country", "Q10": "city", "Q12": "city", "Q20": "person"}


def test_labels_aliases_and_description(built: tuple[ImportedGraph, FakeWikidata]) -> None:
    graph, _ = built
    freedonia = next(node for node in graph.nodes if node.wikidata_id == "Q1")
    assert freedonia.label == "Freedonia"
    assert freedonia.aliases == ["FD", "Freedonien"]
    assert freedonia.description == "fictional country"


def test_relations_only_between_imported_nodes(built: tuple[ImportedGraph, FakeWikidata]) -> None:
    graph, _ = built
    assert graph.relations == [
        Relation("Q1", "CAPITAL", "Q10", "P36"),
        Relation("Q1", "HEAD_OF_STATE", "Q20", "P35", start_year=1990),
        Relation("Q20", "PLACE_OF_BIRTH", "Q10", "P19"),
    ]


def test_years_respect_tiers_rank_and_precision(built: tuple[ImportedGraph, FakeWikidata]) -> None:
    graph, _ = built
    facts = {node.wikidata_id: node.facts for node in graph.nodes}
    assert facts["Q1"]["inception_year"] == 1790  # preferred rank wins
    assert facts["Q10"]["inception_year"] == -44  # 44 BCE
    assert facts["Q20"] == {"year": 1900}  # numeric tier year skipped
    assert "year" not in facts["Q12"]  # century precision skipped


def test_numeric_facts_only_for_famous_entities(built: tuple[ImportedGraph, FakeWikidata]) -> None:
    graph, fake = built
    facts = {node.wikidata_id: node.facts for node in graph.nodes}
    assert facts["Q1"]["population"] == 120  # most recent value
    assert facts["Q1"]["population_year"] == 2010
    assert facts["Q10"]["population"] == 5  # preferred rank beats newer value
    assert facts["Q10"]["population_year"] == 1990
    quantity_queries = [q for q in fake.queries if query_kind(q) == "quantities"]
    assert all("wd:Q20" not in q and "wd:Q12" not in q for q in quantity_queries)


def test_nodes_are_sorted_by_numeric_id(built: tuple[ImportedGraph, FakeWikidata]) -> None:
    graph, _ = built
    assert [node.wikidata_id for node in graph.nodes] == ["Q1", "Q10", "Q12", "Q20"]


def test_excluded_entities_are_skipped_everywhere() -> None:
    fake = FakeWikidata()
    graph = GraphBuilder(make_config(exclude_entities=["Q10", "Q20"]), fake.select).build()
    ids = {node.wikidata_id for node in graph.nodes}
    # Q11 moves up because the excluded Q10 no longer takes the single city slot.
    assert ids == {"Q1", "Q11", "Q12"}
    assert graph.relations == []


def test_entities_cut_by_a_cap_do_not_fall_into_later_types() -> None:
    fake = FakeWikidata()
    config = make_config(
        entity_types={
            "country": {"classes": ["Q6256"]},
            "city": {"classes": ["Q515"], "fame_threshold": 100, "max_entities": 1},
            "town": {"classes": ["Q515"]},
        }
    )
    graph = GraphBuilder(config, fake.select).build()
    assert "town" not in graph.type_counts()
    assert "Q11" not in {node.wikidata_id for node in graph.nodes}


def test_best_rank_only_keeps_current_values(built: tuple[ImportedGraph, FakeWikidata]) -> None:
    graph, _ = built
    capitals = [r.target for r in graph.relations if r.source == "Q1" and r.name == "CAPITAL"]
    # Q12 is only a former capital of Q1; it is still imported as Q2's only capital.
    assert capitals == ["Q10"]
    assert "Q12" in {node.wikidata_id for node in graph.nodes}


def test_mul_label_is_used_when_english_is_missing(
    built: tuple[ImportedGraph, FakeWikidata],
) -> None:
    graph, fake = built
    smallcap = next(node for node in graph.nodes if node.wikidata_id == "Q12")
    assert smallcap.label == "Smallcap"
    assert smallcap.aliases == []
    label_queries = [q for q in fake.queries if query_kind(q) == "labels"]
    assert all('"mul"' in q for q in label_queries)
