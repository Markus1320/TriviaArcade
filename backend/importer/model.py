"""In-memory representation of the imported graph."""

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Node:
    wikidata_id: str
    entity_type: str
    sitelinks: int
    label: str = ""
    description: str | None = None
    aliases: list[str] = field(default_factory=list)
    # Numeric facts and years, keyed by the names configured in import.yaml.
    facts: dict[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True)
class Relation:
    source: str
    name: str
    target: str
    property: str
    start_year: int | None = None
    end_year: int | None = None
    year: int | None = None


@dataclass
class ImportedGraph:
    nodes: list[Node]
    relations: list[Relation]

    def type_counts(self) -> Counter[str]:
        return Counter(node.entity_type for node in self.nodes)

    def relation_counts(self) -> Counter[str]:
        return Counter(relation.name for relation in self.relations)
