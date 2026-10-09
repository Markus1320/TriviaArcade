"""The explore command against canned SPARQL results; no network access."""

from importer.explore import explore_class, format_report
from importer.parsing import ENTITY_PREFIX, Row
from importer.queries import query_kind
from tests.test_importer_build import make_config

ITEM = "http://wikiba.se/ontology#WikibaseItem"
TIME = "http://wikiba.se/ontology#Time"


class FakeWikidata:
    """Three films; P57 (director) on all of them, P577 on two, P36 (configured) on one."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def select(self, query: str) -> list[Row]:
        self.queries.append(query)
        kind = query_kind(query)
        if kind == "entities":
            return [
                {"item": f"{ENTITY_PREFIX}Q1", "sitelinks": "120"},
                {"item": f"{ENTITY_PREFIX}Q2", "sitelinks": "200"},
                {"item": f"{ENTITY_PREFIX}Q3", "sitelinks": "45"},
            ]
        if kind == "property-usage":
            return [
                {"prop": f"{ENTITY_PREFIX}P577", "type": TIME, "n": "2"},
                {"prop": f"{ENTITY_PREFIX}P57", "type": ITEM, "n": "3"},
                {"prop": f"{ENTITY_PREFIX}P36", "type": ITEM, "n": "1"},
            ]
        if kind == "names":
            names = {
                "Q11424": [("en", "film")],
                "Q1": [("en", "Second Film")],
                "Q2": [("mul", "Top Film")],
                "P57": [("en", "director")],
                "P577": [("en", "publication date")],
                "P36": [("en", "capital")],
            }
            return [
                {"s": f"{ENTITY_PREFIX}{key}", "lang": lang, "text": text}
                for key, labels in names.items()
                for lang, text in labels
            ]
        raise AssertionError(f"unexpected query kind: {kind}")


def test_report_counts_ranks_and_lists_properties() -> None:
    wikidata = FakeWikidata()
    report = explore_class(
        wikidata.select, make_config(), "Q11424", thresholds=(100, 40, 150), top=2, sample=3
    )

    assert report.name == "film"
    assert report.counts == [(40, 3), (100, 2), (150, 1)]
    # Most famous first; the language independent label is used when there is no English one.
    assert report.top == [("Q2", "Top Film", 200), ("Q1", "Second Film", 120)]
    assert [(p.pid, p.name, p.kind, p.count) for p in report.properties] == [
        ("P57", "director", "item", 3),
        ("P577", "publication date", "time", 2),
        ("P36", "capital", "item", 1),
    ]
    assert [p.configured for p in report.properties] == [False, False, True]
    # The lowest threshold is the one sent to Wikidata.
    assert "FILTER(?sitelinks >= 40)" in wikidata.queries[0]


def test_classes_can_be_selected_by_another_property() -> None:
    wikidata = FakeWikidata()
    report = explore_class(wikidata.select, make_config(), "Q11424", selected_by="P106")
    assert report.selected_by == "P106"
    assert "?item wdt:P106 wd:Q11424" in wikidata.queries[0]


def test_format_report_marks_configured_and_hides_rare_properties() -> None:
    report = explore_class(FakeWikidata().select, make_config(), "Q11424", top=2, sample=3)
    text = format_report(report, min_share=0.5)
    assert "== film (Q11424), selected by P31 ==" in text
    assert " 1. Top Film (Q2), 200" in text
    assert "3/3  P57    item     director" in text
    assert "P577" in text
    # P36 is on 1 of 3 entities, below the 50% floor.
    assert "P36" not in text


def test_format_report_without_entities() -> None:
    def select(query: str) -> list[Row]:
        if query_kind(query) == "names":
            return [{"s": f"{ENTITY_PREFIX}Q11424", "lang": "en", "text": "film"}]
        return []

    text = format_report(explore_class(select, make_config(), "Q11424"))
    assert "No entities found" in text
