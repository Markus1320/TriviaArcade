"""SPARQL query builders for the Wikidata query service.

Every query starts with a "# kind: <name>" comment. The client uses it to name cache files,
and tests use it to route queries to canned results.

All identifiers interpolated here are validated by the config model (Q-IDs, P-IDs,
language codes), so no user controlled text reaches a query.
"""

from collections.abc import Iterable

from importer.config import DatePropertyConfig, NumericPropertyConfig, RelationConfig

_NOT_DEPRECATED = "?st wikibase:rank ?rank . FILTER(?rank != wikibase:DeprecatedRank)"


def query_kind(query: str) -> str:
    first_line = query.split("\n", 1)[0]
    return first_line.removeprefix("# kind: ").strip()


def _values(ids: Iterable[str]) -> str:
    return " ".join(f"wd:{qid}" for qid in ids)


def entities_of_class(class_qid: str, min_sitelinks: int) -> str:
    return f"""# kind: entities
SELECT ?item ?sitelinks WHERE {{
  ?item wdt:P31 wd:{class_qid} ; wikibase:sitelinks ?sitelinks .
  FILTER(?sitelinks >= {min_sitelinks})
}}"""


def statements(subject_ids: list[str], relations: list[RelationConfig]) -> str:
    props = " ".join(f'("{r.property}" p:{r.property} ps:{r.property})' for r in relations)
    return f"""# kind: statements
SELECT ?s ?pid ?o ?osl ?rank ?start ?end ?pit WHERE {{
  VALUES ?s {{ {_values(subject_ids)} }}
  VALUES (?pid ?p ?ps) {{ {props} }}
  ?s ?p ?st . ?st ?ps ?o .
  {_NOT_DEPRECATED}
  ?o wikibase:sitelinks ?osl .
  OPTIONAL {{ ?st pq:P580 ?start }}
  OPTIONAL {{ ?st pq:P582 ?end }}
  OPTIONAL {{ ?st pq:P585 ?pit }}
}}"""


def classes(ids: list[str]) -> str:
    return f"""# kind: classes
SELECT ?s ?class WHERE {{
  VALUES ?s {{ {_values(ids)} }}
  ?s wdt:P31 ?class .
}}"""


def labels(ids: list[str], languages: list[str]) -> str:
    langs = ", ".join(f'"{lang}"' for lang in languages)
    return f"""# kind: labels
SELECT ?s ?kind ?lang ?text WHERE {{
  VALUES ?s {{ {_values(ids)} }}
  {{ ?s rdfs:label ?text . BIND("label" AS ?kind) }}
  UNION {{ ?s skos:altLabel ?text . BIND("alias" AS ?kind) }}
  UNION {{ ?s schema:description ?text . FILTER(LANG(?text) = "en") BIND("description" AS ?kind) }}
  BIND(LANG(?text) AS ?lang)
  FILTER(?lang IN ({langs}))
}}"""


def dates(ids: list[str], props: list[DatePropertyConfig]) -> str:
    values = " ".join(f'("{d.property}" p:{d.property} psv:{d.property})' for d in props)
    return f"""# kind: dates
SELECT ?s ?pid ?time ?precision ?rank WHERE {{
  VALUES ?s {{ {_values(ids)} }}
  VALUES (?pid ?p ?psv) {{ {values} }}
  ?s ?p ?st . ?st ?psv ?v .
  ?v wikibase:timeValue ?time ; wikibase:timePrecision ?precision .
  {_NOT_DEPRECATED}
}}"""


def quantities(ids: list[str], props: list[NumericPropertyConfig]) -> str:
    values = " ".join(f'("{n.property}" p:{n.property} psv:{n.property})' for n in props)
    return f"""# kind: quantities
SELECT ?s ?pid ?amount ?unit ?pit ?rank WHERE {{
  VALUES ?s {{ {_values(ids)} }}
  VALUES (?pid ?p ?psv) {{ {values} }}
  ?s ?p ?st . ?st ?psv ?v .
  ?v wikibase:quantityAmount ?amount ; wikibase:quantityUnit ?unit .
  {_NOT_DEPRECATED}
  OPTIONAL {{ ?st pq:P585 ?pit }}
}}"""
