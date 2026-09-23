"""Turns a question seed (small subgraph) into plain text facts for the generator."""

from app.graph.model import GraphEdge, GraphNode, QuestionSeed

MAX_ALIASES = 6

# How stored facts are shown. Unknown keys are shown as "key: value".
_QUANTITY_FORMATS = {
    "population": "population {value:,.0f}",
    "area_km2": "area {value:,.0f} km²",
    "length_km": "length {value:,.0f} km",
    "elevation_m": "elevation {value:,.0f} m",
}
_YEAR_LABELS = {
    "year": "year",
    "start_year": "start",
    "end_year": "end",
    "inception_year": "founded",
    "dissolved_year": "dissolved",
    "birth_year": "born",
    "death_year": "died",
}


def format_year(year: int) -> str:
    return f"{-year} BC" if year < 0 else str(year)


def format_seed(seed: QuestionSeed) -> str:
    labels = {node.wikidata_id: node.label for node in seed.nodes}
    lines = ["Entities:"]
    lines += [f"- {_describe_node(node)}" for node in seed.nodes]
    lines += ["", "Relations (walked in this order):"]
    lines += [f"- {_describe_edge(edge, labels)}" for edge in seed.edges]
    return "\n".join(lines)


def _describe_node(node: GraphNode) -> str:
    text = f"{node.label} ({node.entity_type.replace('_', ' ')}"
    if node.description:
        text += f"; {node.description}"
    text += ")"
    facts = _describe_facts(node.facts)
    if facts:
        text += f": {facts}"
    if node.aliases:
        text += f". Also known as: {', '.join(node.aliases[:MAX_ALIASES])}"
    return text


def _describe_facts(facts: dict[str, int | float]) -> str:
    parts = []
    for key, value in sorted(facts.items()):
        if key in _QUANTITY_FORMATS:
            text = _QUANTITY_FORMATS[key].format(value=value)
            reference_year = facts.get(f"{key}_year")
            if reference_year is not None:
                text += f" (as of {format_year(int(reference_year))})"
            parts.append(text)
        elif key.endswith("_year") and key.removesuffix("_year") in _QUANTITY_FORMATS:
            continue  # reference year, shown together with its value
        elif key in _YEAR_LABELS:
            parts.append(f"{_YEAR_LABELS[key]} {format_year(int(value))}")
        else:
            parts.append(f"{key.replace('_', ' ')}: {value}")
    return "; ".join(parts)


def _describe_edge(edge: GraphEdge, labels: dict[str, str]) -> str:
    relation = edge.relation.lower().replace("_", " ")
    text = f"{labels[edge.source]} -- {relation} --> {labels[edge.target]}"
    period = []
    if edge.year is not None:
        period.append(f"in {format_year(edge.year)}")
    if edge.start_year is not None:
        period.append(f"from {format_year(edge.start_year)}")
    if edge.end_year is not None:
        period.append(f"until {format_year(edge.end_year)}")
    if period:
        text += f" ({' '.join(period)})"
    return text
