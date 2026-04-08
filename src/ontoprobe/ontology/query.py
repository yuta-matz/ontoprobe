"""SPARQL queries against the ontology graph."""

from dataclasses import dataclass

from rdflib import Graph

ONT = "http://ontoprobe.example.org/ontology#"


@dataclass
class CausalRule:
    name: str
    label: str
    cause: str
    effect: str
    direction: str
    magnitude: str
    condition: str | None
    compared_to: str | None
    description: str


@dataclass
class MetricMapping:
    concept: str
    dbt_metric: str


def get_causal_rules(graph: Graph) -> list[CausalRule]:
    """Extract all causal rules from the ontology."""
    query = f"""
    PREFIX : <{ONT}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?rule ?label ?cause ?causeLabel ?effect ?effectLabel
           ?direction ?magnitude ?condition ?comparedTo ?comparedToLabel ?description
    WHERE {{
        ?rule a :CausalRule ;
              rdfs:label ?label ;
              :hasCause ?cause ;
              :hasEffect ?effect ;
              :hasDirection ?direction ;
              :hasDescription ?description .
        ?cause rdfs:label ?causeLabel .
        ?effect rdfs:label ?effectLabel .
        OPTIONAL {{ ?rule :hasExpectedMagnitude ?magnitude }}
        OPTIONAL {{ ?rule :hasCondition ?condition }}
        OPTIONAL {{
            ?rule :hasComparedTo ?comparedTo .
            ?comparedTo rdfs:label ?comparedToLabel .
        }}
    }}
    ORDER BY ?rule
    """
    results = graph.query(query)
    rules = []
    for row in results:
        rules.append(CausalRule(
            name=str(row.rule).replace(ONT, ""),
            label=str(row.label),
            cause=str(row.causeLabel),
            effect=str(row.effectLabel),
            direction=str(row.direction),
            magnitude=str(row.magnitude) if row.magnitude else "",
            condition=str(row.condition) if row.condition else None,
            compared_to=str(row.comparedToLabel) if row.comparedToLabel else None,
            description=str(row.description),
        ))
    return rules


def get_metric_mappings(graph: Graph) -> list[MetricMapping]:
    """Extract metric-to-dbt-metric mappings from the ontology."""
    query = f"""
    PREFIX : <{ONT}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?concept ?label ?dbtMetric
    WHERE {{
        ?concept a :Metric ;
                 rdfs:label ?label ;
                 :measuredBy ?dbtMetric .
    }}
    ORDER BY ?concept
    """
    results = graph.query(query)
    return [
        MetricMapping(concept=str(row.label), dbt_metric=str(row.dbtMetric))
        for row in results
    ]


def format_ontology_context(rules: list[CausalRule], mappings: list[MetricMapping]) -> str:
    """Format ontology knowledge as text for LLM context."""
    lines = ["## Domain Knowledge (Ontology)\n"]

    lines.append("### Causal Rules")
    for i, rule in enumerate(rules, 1):
        lines.append(f"\n**Rule {i}: {rule.label}**")
        lines.append(f"  - Cause: {rule.cause}")
        lines.append(f"  - Effect on: {rule.effect}")
        lines.append(f"  - Direction: {rule.direction}")
        if rule.magnitude:
            lines.append(f"  - Expected magnitude: {rule.magnitude}")
        if rule.condition:
            lines.append(f"  - Condition: {rule.condition}")
        if rule.compared_to:
            lines.append(f"  - Compared to: {rule.compared_to}")
        lines.append(f"  - {rule.description}")

    lines.append("\n### Metric Mappings")
    lines.append("Ontology concepts mapped to dbt metrics:")
    for m in mappings:
        lines.append(f"  - {m.concept} → `{m.dbt_metric}`")

    return "\n".join(lines)
