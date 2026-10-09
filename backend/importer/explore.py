"""Look at candidate entity types on Wikidata before adding them to config/import.yaml.

    python -m importer.explore Q11424 Q7889             # film, video game (instance of)
    python -m importer.explore --by P106 Q11900058      # people with the occupation explorer
    python -m importer.explore --by P39 Q842606         # people who held the position Roman emperor

For every class it prints how many entities reach several fame thresholds, the most famous
names, and which properties those entities carry (candidates for relations and facts).
Nothing is written to Neo4j. Responses are cached like the importer's.
"""

import argparse
import io
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from importer import queries
from importer.config import ImportConfig, load_config
from importer.parsing import ENTITY_PREFIX, Row, chunks, entity_id
from importer.settings import PROJECT_ROOT
from importer.sparql import SparqlClient, SparqlError

SelectFn = Callable[[str], list[Row]]

DEFAULT_THRESHOLDS = (40, 60, 80, 100, 150, 200)
_QID = re.compile(r"^Q\d+$")
_PID = re.compile(r"^P\d+$")
_NAME_BATCH = 100
# Short names for Wikidata's property types.
_PROPERTY_KINDS = {
    "http://wikiba.se/ontology#WikibaseItem": "item",
    "http://wikiba.se/ontology#Time": "time",
    "http://wikiba.se/ontology#Quantity": "quantity",
}


@dataclass(frozen=True)
class PropertyUsage:
    pid: str
    name: str
    kind: str  # item (possible relation), time (year) or quantity (number)
    count: int
    configured: bool


@dataclass(frozen=True)
class ClassReport:
    qid: str
    name: str
    selected_by: str
    # (threshold, number of entities at or above it), lowest threshold first
    counts: list[tuple[int, int]]
    # (Q-ID, name, sitelinks), most famous first
    top: list[tuple[str, str, int]]
    sample_size: int
    properties: list[PropertyUsage]


def explore_class(
    select: SelectFn,
    config: ImportConfig,
    qid: str,
    *,
    selected_by: str = "P31",
    include_subclasses: bool = False,
    thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS,
    top: int = 20,
    sample: int = 50,
) -> ClassReport:
    ordered = sorted(thresholds)
    rows = select(queries.entities_of_class(qid, ordered[0], selected_by, include_subclasses))
    fame = {entity_id(row["item"]): int(row["sitelinks"]) for row in rows}
    ranked = sorted(fame, key=lambda item: (-fame[item], item))
    counts = [(t, sum(1 for value in fame.values() if value >= t)) for t in ordered]

    sample_ids = ranked[:sample]
    usage_rows = select(queries.property_usage(sample_ids)) if sample_ids else []
    usage = [
        (entity_id(row["prop"]), _PROPERTY_KINDS.get(row["type"], "other"), int(row["n"]))
        for row in usage_rows
    ]
    labels = _names(select, [qid, *ranked[:top], *(pid for pid, _, _ in usage)])

    configured = _configured_properties(config)
    properties = [
        PropertyUsage(pid, labels.get(pid, pid), kind, count, pid in configured)
        for pid, kind, count in sorted(usage, key=lambda u: (-u[2], u[0]))
    ]
    return ClassReport(
        qid=qid,
        name=labels.get(qid, qid),
        selected_by=selected_by,
        counts=counts,
        top=[(item, labels.get(item, item), fame[item]) for item in ranked[:top]],
        sample_size=len(sample_ids),
        properties=properties,
    )


def format_report(report: ClassReport, *, min_share: float = 0.3) -> str:
    """Plain text for the terminal; properties on less than min_share of the sample are omitted."""
    lines = [f"== {report.name} ({report.qid}), selected by {report.selected_by} =="]
    lines.append("Entities at or above a fame threshold (sitelinks):")
    lines += [f"  >= {threshold:>3}: {count:>6}" for threshold, count in report.counts]
    if not report.top:
        lines.append("No entities found. Check the Q-ID and the --by property.")
        return "\n".join(lines)

    lines.append(f"Most famous {len(report.top)}:")
    lines += [
        f"  {rank:>2}. {name} ({qid}), {sitelinks}"
        for rank, (qid, name, sitelinks) in enumerate(report.top, start=1)
    ]
    lines.append(
        f"Properties on the {report.sample_size} most famous "
        "(item = possible relation, time = year, quantity = number, * = already in import.yaml):"
    )
    floor = min_share * report.sample_size
    for usage in report.properties:
        if usage.count < floor:
            continue
        mark = "*" if usage.configured else " "
        share = f"{usage.count:>3}/{report.sample_size}"
        lines.append(f" {mark}{share}  {usage.pid:<6} {usage.kind:<8} {usage.name}")
    return "\n".join(lines)


def _names(select: SelectFn, ids: list[str]) -> dict[str, str]:
    """English labels, falling back to the language independent one."""
    found: dict[str, dict[str, str]] = {}
    for batch in chunks(list(dict.fromkeys(ids)), _NAME_BATCH):
        for row in select(queries.names(batch)):
            key = row["s"].removeprefix(ENTITY_PREFIX)
            found.setdefault(key, {})[row["lang"]] = row["text"]
    return {key: texts.get("en") or texts["mul"] for key, texts in found.items()}


def _configured_properties(config: ImportConfig) -> set[str]:
    return (
        {relation.property for relation in config.relations}
        | {numeric.property for numeric in config.numeric_properties}
        | {date.property for date in config.date_properties}
    )


def _qid(value: str) -> str:
    if not _QID.match(value):
        raise argparse.ArgumentTypeError(f"not a Wikidata Q-ID: {value}")
    return value


def _pid(value: str) -> str:
    if not _PID.match(value):
        raise argparse.ArgumentTypeError(f"not a Wikidata P-ID: {value}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m importer.explore",
        description="Show counts, top names and common properties of Wikidata classes.",
    )
    parser.add_argument("classes", nargs="+", type=_qid, metavar="QID")
    parser.add_argument(
        "--by",
        type=_pid,
        default="P31",
        metavar="PID",
        help="property that links entities to the class: P31 instance of (default), "
        "P106 occupation, P39 position held",
    )
    parser.add_argument(
        "--subclasses",
        action="store_true",
        help="also count entities of subclasses, e.g. inner planets for planet (slower)",
    )
    parser.add_argument("--thresholds", nargs="+", type=int, default=list(DEFAULT_THRESHOLDS))
    parser.add_argument("--top", type=int, default=20, help="number of names to list")
    parser.add_argument("--sample", type=int, default=50, help="entities checked for properties")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config" / "import.yaml")
    parser.add_argument("--cache-dir", type=Path, default=PROJECT_ROOT / "data" / "raw")
    parser.add_argument("--refresh", action="store_true", help="ignore cached responses")
    args = parser.parse_args(argv)
    # Names contain characters a Windows console code page may not have.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    config = load_config(args.config)
    client = SparqlClient(config.wikidata, args.cache_dir, refresh=args.refresh)
    failed = False
    try:
        for qid in args.classes:
            try:
                report = explore_class(
                    client.select,
                    config,
                    qid,
                    selected_by=args.by,
                    include_subclasses=args.subclasses,
                    thresholds=tuple(args.thresholds),
                    top=args.top,
                    sample=args.sample,
                )
            except SparqlError as error:
                # Very large classes can time out on the public endpoint.
                print(f"== {qid}: query failed: {error}\n")
                failed = True
                continue
            print(format_report(report) + "\n")
    finally:
        client.close()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
