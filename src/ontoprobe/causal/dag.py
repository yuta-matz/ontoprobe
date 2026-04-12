"""Convert ontology causal rules to a networkx DAG."""

from __future__ import annotations

import networkx as nx

from ontoprobe.ontology.loader import load_ontology
from ontoprobe.ontology.query import get_causal_rules, CausalRule


def build_causal_dag(rules: list[CausalRule] | None = None) -> nx.DiGraph:
    """Build a directed graph from ontology causal rules.

    Each node is a concept (cause or effect). Each edge carries the rule metadata
    including direction and expected magnitude.
    """
    if rules is None:
        graph = load_ontology()
        rules = get_causal_rules(graph)

    dag = nx.DiGraph()

    for rule in rules:
        dag.add_edge(
            rule.cause,
            rule.effect,
            label=rule.label,
            direction=rule.direction,
            magnitude=rule.magnitude,
            condition=rule.condition,
            compared_to=rule.compared_to,
            description=rule.description,
        )

    return dag


def get_ancestors(dag: nx.DiGraph, node: str) -> list[str]:
    """Get all ancestor nodes (potential causes) for a given effect."""
    return list(nx.ancestors(dag, node))


def get_causal_paths(dag: nx.DiGraph, source: str, target: str) -> list[list[str]]:
    """Find all causal paths from source to target."""
    return list(nx.all_simple_paths(dag, source, target))


def print_dag_summary(dag: nx.DiGraph) -> None:
    """Print a summary of the causal DAG."""
    print(f"Causal DAG: {dag.number_of_nodes()} nodes, {dag.number_of_edges()} edges")
    for u, v, data in dag.edges(data=True):
        mag = data.get("magnitude", "?")
        print(f"  {u} → {v}  (direction: {data['direction']}, magnitude: {mag})")


if __name__ == "__main__":
    dag = build_causal_dag()
    print_dag_summary(dag)
