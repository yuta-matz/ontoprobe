"""Evaluation helpers for the root-cause loop ablation.

Uses the existing ontology causal DAG to compute whether the metrics an
agent queried during an investigation lie on the causal path from the
(hidden) ground truth concept to the (observed) anomaly concept, and
whether the agent's reported root cause matches ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx

from ontoprobe.causal.dag import build_causal_dag
from ontoprobe.ontology.loader import load_ontology
from ontoprobe.rootcause.tools import METRIC_ALIAS, _FRIENDLY_TO_OPAQUE

ONT = "http://ontoprobe.example.org/ontology#"


def concept_to_metric_map() -> dict[str, str]:
    """Concept label → opaque metric id, via the ontology's measuredBy."""
    graph = load_ontology()
    query = f"""
    PREFIX : <{ONT}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    SELECT ?label ?metric WHERE {{
        ?c rdfs:label ?label ;
           :measuredBy ?metric .
    }}
    """
    out: dict[str, str] = {}
    for row in graph.query(query):
        friendly = str(row.metric)
        opaque = _FRIENDLY_TO_OPAQUE.get(friendly)
        if opaque:
            out[str(row.label)] = opaque
    return out


def on_path_metrics(
    anomaly_concept: str, ground_truth_concept: str
) -> tuple[set[str], set[str]]:
    """Return (gt_path_metrics, any_ancestor_metrics).

    gt_path_metrics: metric ids lying on any simple path from the shocked
        concept to the observed anomaly concept in the causal DAG — these
        are the 'correct' metrics for the agent to query.
    any_ancestor_metrics: metric ids of every ancestor of the anomaly
        concept (plus the anomaly itself) — a more forgiving baseline.
    """
    dag = build_causal_dag()
    cm = concept_to_metric_map()

    gt_path_concepts: set[str] = set()
    if (
        ground_truth_concept in dag.nodes
        and anomaly_concept in dag.nodes
    ):
        try:
            for path in nx.all_simple_paths(
                dag, source=ground_truth_concept, target=anomaly_concept
            ):
                gt_path_concepts.update(path)
        except nx.NodeNotFound:
            pass

    ancestor_concepts: set[str] = set()
    if anomaly_concept in dag.nodes:
        ancestor_concepts = set(nx.ancestors(dag, anomaly_concept)) | {anomaly_concept}

    gt_path_metrics = {cm[c] for c in gt_path_concepts if c in cm}
    ancestor_metrics = {cm[c] for c in ancestor_concepts if c in cm}
    return gt_path_metrics, ancestor_metrics


@dataclass
class TraceStats:
    hit: bool
    reported_concept: str
    iterations: int
    tool_calls: int
    compare_calls: int
    list_parent_calls: int
    queried_metrics: list[str]
    on_gt_path_queries: int
    on_any_ancestor_queries: int
    wrong_branch_queries: int
    precision_gt_path: float | None
    precision_any_ancestor: float | None
    stopped_reason: str
    cost_usd: float


def summarize_trace(
    trace, anomaly_concept: str, ground_truth_concept: str
) -> TraceStats:
    from collections import Counter

    counts = Counter(c["tool"] for c in trace.tool_calls)
    compare_calls = [c for c in trace.tool_calls if c["tool"] == "compare_metric_round"]
    queried_metrics = [
        c["input"].get("metric_id")
        for c in compare_calls
        if c["input"].get("metric_id") in METRIC_ALIAS
    ]

    gt_metrics, ancestor_metrics = on_path_metrics(
        anomaly_concept, ground_truth_concept
    )
    on_gt = sum(1 for m in queried_metrics if m in gt_metrics)
    on_anc = sum(1 for m in queried_metrics if m in ancestor_metrics)
    n = len(queried_metrics)
    precision_gt = (on_gt / n) if n else None
    precision_anc = (on_anc / n) if n else None
    wrong = n - on_anc

    hit = False
    reported_concept = ""
    if trace.final_report:
        reported_concept = trace.final_report.get("root_cause_concept", "") or ""
        hit = ground_truth_concept.lower() in reported_concept.lower()

    return TraceStats(
        hit=hit,
        reported_concept=reported_concept,
        iterations=trace.iterations,
        tool_calls=len(trace.tool_calls),
        compare_calls=len(compare_calls),
        list_parent_calls=counts.get("list_parent_causes", 0),
        queried_metrics=queried_metrics,
        on_gt_path_queries=on_gt,
        on_any_ancestor_queries=on_anc,
        wrong_branch_queries=wrong,
        precision_gt_path=precision_gt,
        precision_any_ancestor=precision_anc,
        stopped_reason=trace.stopped_reason,
        cost_usd=trace.total_cost_usd,
    )
