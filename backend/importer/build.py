"""Builds the knowledge graph from Wikidata query results.

Steps:
1. Seeds: entities of the configured types that pass their fame threshold.
2. Statements: allowlisted relations of the seeds.
3. Reached entities: relation targets outside the seeds that pass the target threshold
   and can be classified into a configured type.
4. Statements of reached entities for relations marked from_related (no further growth).
5. Labels, aliases and descriptions; entities without an English (or fallback) label are
   dropped.
6. Years and numeric facts, respecting the base and numeric tiers.
7. Relations between entities that made it into the graph.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from importer import queries
from importer.config import ImportConfig, RelationConfig
from importer.model import ImportedGraph, Node, Relation
from importer.parsing import (
    YEAR_PRECISION,
    Row,
    build_aliases,
    chunks,
    convert_quantity,
    entity_id,
    is_preferred,
    parse_year,
)

logger = logging.getLogger(__name__)

SelectFn = Callable[[str], list[Row]]


@dataclass(frozen=True)
class _Statement:
    subject: str
    relation: RelationConfig
    target: str
    target_sitelinks: int
    preferred: bool
    start_year: int | None
    end_year: int | None
    year: int | None


class GraphBuilder:
    def __init__(self, config: ImportConfig, select: SelectFn) -> None:
        self._config = config
        self._select = select

    def build(self) -> ImportedGraph:
        nodes = self._fetch_seeds()
        seed_ids = sorted(nodes)
        logger.info("Seeds: %d entities", len(seed_ids))

        statements = self._fetch_statements(seed_ids, self._config.relations)
        self._add_reached_entities(nodes, statements)
        reached_ids = sorted(nodes.keys() - set(seed_ids))
        logger.info("Reached through relations: %d entities", len(reached_ids))

        related_relations = [r for r in self._config.relations if r.from_related]
        if reached_ids and related_relations:
            statements += self._fetch_statements(reached_ids, related_relations)

        self._fetch_labels(nodes)
        unlabeled = [qid for qid, node in nodes.items() if not node.label]
        for qid in unlabeled:
            del nodes[qid]
        if unlabeled:
            logger.info("Dropped %d entities without English or fallback label", len(unlabeled))

        self._fetch_dates(nodes)
        self._fetch_quantities(nodes)

        relations = _relations_within(nodes, statements)
        return ImportedGraph(
            nodes=sorted(nodes.values(), key=lambda n: _qid_number(n.wikidata_id)),
            relations=relations,
        )

    # 1. Seeds

    def _fetch_seeds(self) -> dict[str, Node]:
        nodes: dict[str, Node] = {}
        # Entities matched by an earlier type stay claimed even when its cap drops them.
        claimed = set(self._config.exclude_entities)
        for type_name, type_config in self._config.entity_types.items():
            threshold = self._config.type_fame_threshold(type_name)
            candidates: dict[str, int] = {}
            for class_qid in type_config.classes:
                for row in self._select(queries.entities_of_class(class_qid, threshold)):
                    qid = entity_id(row["item"])
                    if qid not in claimed:
                        candidates[qid] = int(row["sitelinks"])
            claimed.update(candidates)

            ranked = sorted(candidates.items(), key=lambda item: (-item[1], item[0]))
            if type_config.max_entities is not None:
                ranked = ranked[: type_config.max_entities]
            for qid, sitelinks in ranked:
                nodes[qid] = Node(wikidata_id=qid, entity_type=type_name, sitelinks=sitelinks)
            logger.info("  %-18s %5d (threshold %d)", type_name, len(ranked), threshold)
        return nodes

    # 2. and 4. Statements

    def _fetch_statements(
        self, subject_ids: list[str], relations: list[RelationConfig]
    ) -> list[_Statement]:
        by_property = {r.property: r for r in relations}
        result: list[_Statement] = []
        for batch in chunks(subject_ids, self._config.wikidata.batch_size):
            for row in self._select(queries.statements(batch, relations)):
                result.append(
                    _Statement(
                        subject=entity_id(row["s"]),
                        relation=by_property[row["pid"]],
                        target=entity_id(row["o"]),
                        target_sitelinks=int(row["osl"]),
                        preferred=is_preferred(row.get("rank")),
                        start_year=parse_year(row.get("start")),
                        end_year=parse_year(row.get("end")),
                        year=parse_year(row.get("pit")),
                    )
                )
        return _keep_best_rank(result)

    # 3. Reached entities

    def _add_reached_entities(self, nodes: dict[str, Node], statements: list[_Statement]) -> None:
        candidates: dict[str, int] = {}
        fallbacks: dict[str, str] = {}
        for statement in statements:
            target = statement.target
            if target in nodes or target in self._config.exclude_entities:
                continue
            if statement.target_sitelinks < self._config.target_fame_threshold(statement.relation):
                continue
            candidates[target] = statement.target_sitelinks
            fallback = statement.relation.fallback_target_type
            if fallback is not None:
                fallbacks.setdefault(target, fallback)

        types = self._classify(sorted(candidates))
        for qid, sitelinks in candidates.items():
            type_name = types.get(qid) or fallbacks.get(qid)
            if type_name is not None:
                nodes[qid] = Node(wikidata_id=qid, entity_type=type_name, sitelinks=sitelinks)

    def _classify(self, ids: list[str]) -> dict[str, str]:
        class_to_type = self._config.class_to_type()
        type_order = list(self._config.entity_types) + list(self._config.related_types)
        result: dict[str, str] = {}
        for batch in chunks(ids, self._config.wikidata.batch_size):
            for row in self._select(queries.classes(batch)):
                qid = entity_id(row["s"])
                type_name = class_to_type.get(entity_id(row["class"]))
                if type_name is None:
                    continue
                current = result.get(qid)
                if current is None or type_order.index(type_name) < type_order.index(current):
                    result[qid] = type_name
        return result

    # 5. Labels

    def _fetch_labels(self, nodes: dict[str, Node]) -> None:
        # Main label: English, else the first fallback language that has one.
        label_order = ["en", *self._config.label_fallback_languages]
        main_labels: dict[str, dict[str, str]] = {qid: {} for qid in nodes}
        candidates: dict[str, list[str]] = {qid: [] for qid in nodes}
        languages = self._config.label_languages()
        for batch in chunks(sorted(nodes), self._config.wikidata.label_batch_size):
            for row in self._select(queries.labels(batch, languages)):
                qid = entity_id(row["s"])
                kind, lang, text = row["kind"], row["lang"], row["text"]
                if kind == "description":
                    nodes[qid].description = text
                    continue
                if kind == "label" and lang in label_order:
                    main_labels[qid][lang] = text
                candidates[qid].append(text)
        for qid, node in nodes.items():
            found = main_labels[qid]
            label = next((found[lang] for lang in label_order if lang in found), "")
            node.label = label
            if label:
                node.aliases = build_aliases(label, sorted(candidates[qid]))

    # 6. Years and numeric facts

    def _fetch_dates(self, nodes: dict[str, Node]) -> None:
        props = {d.property: d for d in self._config.date_properties}
        if not props:
            return
        # (qid, name) -> (preferred, year); preferred rank wins, then the earliest year.
        best: dict[tuple[str, str], tuple[bool, int]] = {}
        for batch in chunks(sorted(nodes), self._config.wikidata.batch_size):
            for row in self._select(queries.dates(batch, list(props.values()))):
                node = nodes[entity_id(row["s"])]
                prop = props[row["pid"]]
                if prop.tier == "numeric" and not self._is_numeric_tier(node):
                    continue
                if int(row["precision"]) < YEAR_PRECISION:
                    continue
                year = parse_year(row["time"])
                if year is None:
                    continue
                candidate = (is_preferred(row.get("rank")), year)
                key = (node.wikidata_id, prop.name)
                current = best.get(key)
                if current is None or _better_date(candidate, current):
                    best[key] = candidate
        for (qid, name), (_, year) in best.items():
            nodes[qid].facts[name] = year

    def _fetch_quantities(self, nodes: dict[str, Node]) -> None:
        props = {n.property: n for n in self._config.numeric_properties}
        eligible = sorted(qid for qid, node in nodes.items() if self._is_numeric_tier(node))
        if not props or not eligible:
            return
        # (qid, name) -> (preferred, reference year, value); preferred, then most recent.
        best: dict[tuple[str, str], tuple[bool, int, float]] = {}
        for batch in chunks(eligible, self._config.wikidata.batch_size):
            for row in self._select(queries.quantities(batch, list(props.values()))):
                prop = props[row["pid"]]
                value = convert_quantity(
                    row["amount"], row["unit"], prop.unit, self._config.unit_conversions
                )
                if value is None:
                    continue
                reference_year = parse_year(row.get("pit"))
                candidate = (
                    is_preferred(row.get("rank")),
                    reference_year if reference_year is not None else -(10**6),
                    value,
                )
                key = (entity_id(row["s"]), prop.name)
                if key not in best or candidate > best[key]:
                    best[key] = candidate

        by_name = {n.name: n for n in self._config.numeric_properties}
        for (qid, name), (_, reference_year, value) in best.items():
            facts = nodes[qid].facts
            facts[name] = int(value) if value.is_integer() else round(value, 2)
            if by_name[name].with_year and reference_year > -(10**6):
                facts[f"{name}_year"] = reference_year

    def _is_numeric_tier(self, node: Node) -> bool:
        return node.sitelinks >= self._config.numeric_fame_threshold


def _keep_best_rank(statements: list[_Statement]) -> list[_Statement]:
    """Apply best_rank_only: drop normal statements where a preferred one exists."""
    has_preferred = {
        (s.subject, s.relation.property)
        for s in statements
        if s.relation.best_rank_only and s.preferred
    }
    return [
        s
        for s in statements
        if s.preferred
        or not s.relation.best_rank_only
        or (s.subject, s.relation.property) not in has_preferred
    ]


def _better_date(candidate: tuple[bool, int], current: tuple[bool, int]) -> bool:
    if candidate[0] != current[0]:
        return candidate[0]
    return candidate[1] < current[1]


def _relations_within(nodes: dict[str, Node], statements: list[_Statement]) -> list[Relation]:
    relations = {
        Relation(
            source=s.subject,
            name=s.relation.name,
            target=s.target,
            property=s.relation.property,
            start_year=s.start_year,
            end_year=s.end_year,
            year=s.year,
        )
        for s in statements
        if s.subject in nodes and s.target in nodes and s.subject != s.target
    }
    return sorted(relations, key=lambda r: (r.source, r.name, r.target, str(r)))


def _qid_number(qid: str) -> int:
    return int(qid[1:])
