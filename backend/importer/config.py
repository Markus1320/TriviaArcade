"""Typed model of config/import.yaml."""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Qid = Annotated[str, StringConstraints(pattern=r"^Q\d+$")]
Pid = Annotated[str, StringConstraints(pattern=r"^P\d+$")]
TypeName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z_]*$")]
PropertyName = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]*$")]
RelationName = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z_]*$")]
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}(-[a-z]+)?$")]

# Node properties written by the importer itself; configured names must not collide.
RESERVED_NODE_PROPERTIES = frozenset(
    {"wikidata_id", "label", "description", "aliases", "sitelinks", "entity_type", "seq"}
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WikidataConfig(_Strict):
    endpoint: str
    user_agent: str = Field(min_length=10)
    min_interval_seconds: float = Field(ge=0)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    batch_size: int = Field(gt=0)
    label_batch_size: int = Field(gt=0)


class EntityTypeConfig(_Strict):
    classes: list[Qid] = Field(min_length=1)
    fame_threshold: int | None = Field(default=None, ge=0)
    max_entities: int | None = Field(default=None, gt=0)


class RelatedTypeConfig(_Strict):
    classes: list[Qid] = Field(min_length=1)


class RelationConfig(_Strict):
    property: Pid
    name: RelationName
    target_fame_threshold: int | None = Field(default=None, ge=0)
    fallback_target_type: TypeName | None = None
    from_related: bool = False
    # Keep only the statements Wikidata ranks best (preferred, else normal), i.e. the
    # current value. Without it, historical values such as former capitals are kept too.
    best_rank_only: bool = False


class NumericPropertyConfig(_Strict):
    property: Pid
    name: PropertyName
    unit: str | None
    with_year: bool = False


class DatePropertyConfig(_Strict):
    property: Pid
    name: PropertyName
    tier: Literal["base", "numeric"]


class ImportConfig(_Strict):
    wikidata: WikidataConfig
    languages: list[LanguageCode] = Field(min_length=1)
    # Used for the main label when an entity has no English label. Wikidata stores many
    # names under "mul" (same in many languages) instead of repeating them per language.
    label_fallback_languages: list[LanguageCode] = Field(default_factory=list)
    fame_threshold: int = Field(ge=0)
    related_fame_threshold: int = Field(ge=0)
    numeric_fame_threshold: int = Field(ge=0)
    exclude_entities: frozenset[Qid] = frozenset()
    entity_types: dict[TypeName, EntityTypeConfig] = Field(min_length=1)
    related_types: dict[TypeName, RelatedTypeConfig] = Field(default_factory=dict)
    relations: list[RelationConfig] = Field(min_length=1)
    numeric_properties: list[NumericPropertyConfig] = Field(default_factory=list)
    unit_conversions: dict[str, dict[Qid, float]] = Field(default_factory=dict)
    date_properties: list[DatePropertyConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if "en" not in self.languages:
            raise ValueError("languages must include 'en', it provides the main label")

        overlap = self.entity_types.keys() & self.related_types.keys()
        if overlap:
            raise ValueError(f"types defined as entity and related type: {sorted(overlap)}")

        known_types = self.entity_types.keys() | self.related_types.keys()
        for relation in self.relations:
            fallback = relation.fallback_target_type
            if fallback is not None and fallback not in known_types:
                raise ValueError(f"{relation.name}: unknown fallback_target_type {fallback!r}")

        _require_unique("relation property", [r.property for r in self.relations])
        _require_unique("relation name", [r.name for r in self.relations])

        for numeric in self.numeric_properties:
            if numeric.unit is not None and numeric.unit not in self.unit_conversions:
                raise ValueError(f"{numeric.name}: unit {numeric.unit!r} has no conversions")

        names = [n.name for n in self.numeric_properties]
        names += [f"{n.name}_year" for n in self.numeric_properties if n.with_year]
        names += [d.name for d in self.date_properties]
        _require_unique("node property name", names)
        reserved = RESERVED_NODE_PROPERTIES.intersection(names)
        if reserved:
            raise ValueError(f"reserved node property names used: {sorted(reserved)}")
        return self

    def label_languages(self) -> list[str]:
        return self.languages + [
            lang for lang in self.label_fallback_languages if lang not in self.languages
        ]

    def type_fame_threshold(self, type_name: str) -> int:
        threshold = self.entity_types[type_name].fame_threshold
        return self.fame_threshold if threshold is None else threshold

    def target_fame_threshold(self, relation: RelationConfig) -> int:
        threshold = relation.target_fame_threshold
        return self.related_fame_threshold if threshold is None else threshold

    def class_to_type(self) -> dict[str, str]:
        """Map each class to its type; the first configured type wins."""
        mapping: dict[str, str] = {}
        all_types: list[tuple[str, list[str]]] = [
            (name, t.classes) for name, t in self.entity_types.items()
        ]
        all_types += [(name, t.classes) for name, t in self.related_types.items()]
        for name, classes in all_types:
            for qid in classes:
                mapping.setdefault(qid, name)
        return mapping


def _require_unique(what: str, values: list[str]) -> None:
    duplicates = sorted({v for v in values if values.count(v) > 1})
    if duplicates:
        raise ValueError(f"duplicate {what}: {duplicates}")


def load_config(path: Path) -> ImportConfig:
    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)
    return ImportConfig.model_validate(data)
