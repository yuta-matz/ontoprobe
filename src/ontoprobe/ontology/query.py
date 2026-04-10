"""SPARQL queries against the ontology graph."""

from dataclasses import dataclass, field

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


@dataclass
class CausalChain:
    """A multi-hop causal chain extracted from the ontology."""

    rules: list[CausalRule] = field(default_factory=list)
    start_cause: str = ""
    end_effect: str = ""
    hop_count: int = 0


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


def _build_rule_index(graph: Graph) -> dict[str, CausalRule]:
    """Build an index of rule name -> CausalRule for chain assembly."""
    rules = get_causal_rules(graph)
    return {r.name: r for r in rules}


def get_causal_chains(graph: Graph) -> list[CausalChain]:
    """Extract multi-hop causal chains using SPARQL property paths.

    Finds all chains of 2+ rules connected via :feedsInto relationships.
    """
    query = f"""
    PREFIX : <{ONT}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?start ?end
    WHERE {{
        ?start :feedsInto+ ?end .
        FILTER NOT EXISTS {{ ?other :feedsInto ?start }}
    }}
    """
    results = graph.query(query)
    rule_index = _build_rule_index(graph)

    # Build chains by walking feedsInto from each start rule
    chain_starts: set[str] = set()
    for row in results:
        start_name = str(row.start).replace(ONT, "")
        chain_starts.add(start_name)

    chains: list[CausalChain] = []
    for start_name in sorted(chain_starts):
        # Walk the chain from this start
        chain_rules: list[CausalRule] = []
        current = start_name
        while current in rule_index:
            chain_rules.append(rule_index[current])
            # Find next rule via feedsInto
            next_query = f"""
            PREFIX : <{ONT}>
            SELECT ?next WHERE {{
                :{current} :feedsInto ?next .
            }}
            """
            next_results = list(graph.query(next_query))
            if next_results:
                current = str(next_results[0].next).replace(ONT, "")
            else:
                break

        if len(chain_rules) >= 2:
            chains.append(CausalChain(
                rules=chain_rules,
                start_cause=chain_rules[0].cause,
                end_effect=chain_rules[-1].effect,
                hop_count=len(chain_rules),
            ))

    return chains


def get_chain_for_effect(graph: Graph, effect_label: str) -> list[CausalChain]:
    """Find all causal chains leading to a specific effect (reverse reasoning)."""
    all_chains = get_causal_chains(graph)
    return [c for c in all_chains if c.end_effect == effect_label]
