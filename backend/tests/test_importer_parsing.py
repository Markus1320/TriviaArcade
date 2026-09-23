import pytest

from importer.loader import node_record, relation_properties, type_label
from importer.model import Node, Relation
from importer.parsing import (
    ENTITY_PREFIX,
    build_aliases,
    chunks,
    convert_quantity,
    entity_id,
    parse_year,
)

CONVERSIONS = {"km2": {"Q712226": 1.0, "Q232291": 2.589988}}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1789-07-14T00:00:00Z", 1789),
        ("+1789-07-14T00:00:00Z", 1789),
        ("-0043-03-15T00:00:00Z", -44),  # XSD 1.1: -0043 is 44 BCE
        ("0000-01-01T00:00:00Z", -1),  # year 0 is 1 BCE
        ("-2560-01-01T00:00:00Z", -2561),
        (None, None),
        ("", None),
        ("not a date", None),
    ],
)
def test_parse_year(value: str | None, expected: int | None) -> None:
    assert parse_year(value) == expected


def test_entity_id() -> None:
    assert entity_id(ENTITY_PREFIX + "Q64") == "Q64"
    with pytest.raises(ValueError, match="not a Wikidata entity URI"):
        entity_id("http://example.com/Q64")


def test_convert_quantity() -> None:
    assert convert_quantity("891.8", ENTITY_PREFIX + "Q712226", "km2", CONVERSIONS) == 891.8
    square_miles = convert_quantity("10", ENTITY_PREFIX + "Q232291", "km2", CONVERSIONS)
    assert square_miles == pytest.approx(25.89988)
    assert convert_quantity("5", ENTITY_PREFIX + "Q11573", "km2", CONVERSIONS) is None
    assert convert_quantity("3677472", ENTITY_PREFIX + "Q199", None, CONVERSIONS) == 3677472


def test_build_aliases_dedupes_case_insensitively_and_drops_label() -> None:
    aliases = build_aliases("Germany", ["Deutschland", "germany", " BRD ", "deutschland", ""])
    assert aliases == ["Deutschland", "BRD"]


def test_chunks() -> None:
    assert list(chunks(["a", "b", "c"], 2)) == [["a", "b"], ["c"]]


def test_type_label() -> None:
    assert type_label("historical_state") == "HistoricalState"
    assert type_label("city") == "City"


def test_node_record_contains_facts_and_seq() -> None:
    node = Node("Q64", "city", 300, label="Berlin", aliases=["Berlin"], facts={"population": 1})
    record = node_record(node, seq=7)
    assert record["seq"] == 7
    assert record["population"] == 1
    assert record["wikidata_id"] == "Q64"


def test_relation_properties_skip_missing_years() -> None:
    relation = Relation("Q1", "HEAD_OF_STATE", "Q2", "P35", start_year=1990)
    assert relation_properties(relation) == {"property": "P35", "start_year": 1990}
