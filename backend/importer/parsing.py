"""Pure helpers that turn SPARQL result values into clean Python values."""

import re
from collections.abc import Iterable

ENTITY_PREFIX = "http://www.wikidata.org/entity/"
PREFERRED_RANK = "http://wikiba.se/ontology#PreferredRank"

# Wikidata time precision 9 means "year"; lower values are decades, centuries, ...
YEAR_PRECISION = 9

_YEAR_PATTERN = re.compile(r"^([+-]?)(\d+)-")

Row = dict[str, str]


def entity_id(uri: str) -> str:
    """Return the Q-ID of a Wikidata entity URI."""
    if not uri.startswith(ENTITY_PREFIX):
        raise ValueError(f"not a Wikidata entity URI: {uri}")
    return uri.removeprefix(ENTITY_PREFIX)


def parse_year(value: str | None) -> int | None:
    """Parse the year of an xsd:dateTime from the Wikidata query service.

    The service follows XSD 1.1, where year 0 is 1 BCE and -0043 is 44 BCE.
    The result uses historical numbering without a year 0: 44 BCE becomes -44.
    """
    if not value:
        return None
    match = _YEAR_PATTERN.match(value)
    if match is None:
        return None
    sign, digits = match.groups()
    year = int(digits) * (-1 if sign == "-" else 1)
    return year - 1 if year <= 0 else year


def is_preferred(rank: str | None) -> bool:
    return rank == PREFERRED_RANK


def convert_quantity(
    amount: str, unit_uri: str, target_unit: str | None, conversions: dict[str, dict[str, float]]
) -> float | None:
    """Convert a quantity into the target unit, or None if the unit is not convertible."""
    value = float(amount)
    if target_unit is None:
        return value
    unit = unit_uri.removeprefix(ENTITY_PREFIX)
    factor = conversions[target_unit].get(unit)
    return None if factor is None else value * factor


def build_aliases(label: str, candidates: Iterable[str]) -> list[str]:
    """Deduplicate alias candidates case-insensitively and drop the main label."""
    seen = {label.casefold()}
    aliases: list[str] = []
    for candidate in candidates:
        text = candidate.strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            aliases.append(text)
    return aliases


def chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]
