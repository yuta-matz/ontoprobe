"""Tool implementations for the root-cause agent loop.

All metrics are exposed to the LLM via opaque IDs (m_101 … m_10N) so the
no-ontology baseline cannot short-cut reasoning by reading causal intent
out of friendly metric names like ``total_discount``. Both conditions
receive neutral natural-language descriptions of each metric; only the
with-ontology condition has access to ``list_parent_causes``, which
returns parent concepts along with their opaque metric IDs resolved
through the ontology's ``:measuredBy`` links.

Three tools:

  list_parent_causes(concept_label)
      SPARQL lookup. Returns each CausalRule whose effect matches
      concept_label, with the parent cause concept, the rule label,
      expected magnitude, description, and — if the parent concept has
      a :measuredBy binding — the opaque metric ID the agent can query.

  compare_metric_round(metric_id, round_a, round_b)
      Round-over-round aggregation against rounds.csv. Accepts only
      opaque metric IDs.

  report_root_cause(root_cause_concept, evidence_chain, recommendation)
      Terminal tool.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from ontoprobe.config import DATA_DIR
from ontoprobe.ontology.loader import load_ontology


class CausalFormat(str, Enum):
    """How the causal rule information is delivered to the agent.

    ONTOLOGY   — pulled on demand via list_parent_causes (SPARQL over Turtle).
    JSON_PUSH  — pre-computed as a flat JSON array and embedded in the
                 system prompt; no tool call required.
    PROSE_PUSH — same content rendered as natural language prose embedded
                 in the system prompt.
    DBT_META   — same content attached to each metric in the catalog
                 (mimicking dbt Semantic Layer meta fields).

    Used by the format-comparison experiment to test whether the
    Phase 6 effect is ontology-format-specific or information-specific.
    """

    ONTOLOGY = "ontology"
    JSON_PUSH = "json_push"
    PROSE_PUSH = "prose_push"
    DBT_META = "dbt_meta"


class OntologyMode(str, Enum):
    """Property-ablation mode for list_parent_causes output.

    Progressive tiers (information added at each step):
        NONE                 (T0) list_parent_causes unavailable
        CONCEPTS_ONLY        (T1) + parent concept labels (hasCause/hasEffect)
        STRUCT_AND_METRIC_ID (T2) + metric_id (measuredBy resolution)
        NO_DESC_MAG          (T3) + rule rdfs:label
        FULL                 (T4) + hasDescription + hasExpectedMagnitude

    NO_CLASS_MEASURED_BY is an orthogonal probe that strips metric_id only
    from class-typed (abstract) concepts while keeping everything else.
    """

    FULL = "full"
    NO_CLASS_MEASURED_BY = "no_class_mb"
    NO_DESC_MAG = "no_desc_mag"
    STRUCT_AND_METRIC_ID = "struct_and_metric_id"
    CONCEPTS_ONLY = "concepts_only"
    NONE = "none"

ROOTCAUSE_DIR = DATA_DIR / "rootcause"
ONT = "http://ontoprobe.example.org/ontology#"


def _sum(rows: list[dict], key: str) -> float:
    return float(sum(r[key] for r in rows))


# --- Friendly metric name → aggregation. Internal only. ---
_FRIENDLY_AGGREGATIONS: dict[str, Callable[[list[dict]], float]] = {
    "total_revenue": lambda rows: _sum(rows, "daily_revenue"),
    "gross_revenue": lambda rows: _sum(rows, "daily_gross_revenue"),
    "order_count": lambda rows: _sum(rows, "daily_orders"),
    "average_order_value": lambda rows: (
        _sum(rows, "daily_revenue") / max(1.0, _sum(rows, "daily_orders"))
    ),
    "total_discount": lambda rows: _sum(rows, "daily_discount_amount"),
    "seasonal_revenue": lambda rows: _sum(rows, "daily_seasonal_revenue"),
    "effective_margin": lambda rows: (
        1.0
        - _sum(rows, "daily_discount_amount")
        / max(1.0, _sum(rows, "daily_gross_revenue"))
    ),
    "campaign_day_share": lambda rows: (
        _sum(rows, "has_discount_campaign") / max(1.0, len(rows))
    ),
    "free_ship_day_share": lambda rows: 0.0,  # not simulated in this DGP
    "vip_order_share": lambda rows: (
        _sum(rows, "daily_vip_orders") / max(1.0, _sum(rows, "daily_orders"))
    ),
    "seasonal_item_share": lambda rows: (
        _sum(rows, "daily_seasonal_orders") / max(1.0, _sum(rows, "daily_orders"))
    ),
}

# --- Opaque ID ↔ friendly name mapping exposed to the LLM. ---
METRIC_ALIAS: dict[str, str] = {
    "m_101": "total_revenue",
    "m_102": "gross_revenue",
    "m_103": "order_count",
    "m_104": "average_order_value",
    "m_105": "total_discount",
    "m_106": "effective_margin",
    "m_107": "seasonal_revenue",
    "m_108": "campaign_day_share",
    "m_109": "free_ship_day_share",
    "m_110": "vip_order_share",
    "m_111": "seasonal_item_share",
}
_FRIENDLY_TO_OPAQUE: dict[str, str] = {v: k for k, v in METRIC_ALIAS.items()}

# Neutral descriptions given to BOTH conditions. Kept terse and
# non-causal — no mention of "driven by", "parent of", etc.
METRIC_DESCRIPTIONS: dict[str, str] = {
    "m_101": "Total customer-facing revenue for the period, after discounts are applied.",
    "m_102": "Total customer-facing revenue for the period, before discounts.",
    "m_103": "Total number of orders placed in the period.",
    "m_104": "Average revenue per order (total_revenue / order_count).",
    "m_105": "Total amount of money deducted from orders via discounts.",
    "m_106": "Share of gross revenue retained after discounts (1 − total_discount / gross_revenue).",
    "m_107": "Revenue attributed to items flagged as seasonal.",
    "m_108": "Fraction of days in the period that had an active discount campaign.",
    "m_109": "Fraction of days in the period that had an active free-shipping campaign.",
    "m_110": "Fraction of orders placed by customers in the VIP segment.",
    "m_111": "Fraction of ordered items flagged as seasonal products.",
}


def metric_catalog() -> list[dict[str, str]]:
    """Opaque ID + description list shown to both A and B agents."""
    return [
        {"metric_id": mid, "description": METRIC_DESCRIPTIONS[mid]}
        for mid in sorted(METRIC_ALIAS.keys())
    ]


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "list_parent_causes",
        "description": (
            "Look up direct parent causes of an ontology concept in the causal rule graph. "
            "Returns each parent concept, the rule label, the expected magnitude of the "
            "relationship, a description, and — if available — the opaque metric id that "
            "measures the parent concept so you can query it with compare_metric_round."
        ),
    },
    {
        "name": "compare_metric_round",
        "description": (
            "Compare a semantic-layer metric between two rounds using its opaque metric id. "
            "Returns the aggregate value for each round, the absolute delta, and the "
            "percentage delta (round_b vs round_a)."
        ),
    },
    {
        "name": "report_root_cause",
        "description": (
            "Terminate the investigation and report the identified root cause with an "
            "ordered evidence chain and a concrete next-round recommendation."
        ),
    },
]


def _coerce(value: str) -> Any:
    if value == "":
        return value
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _load_rounds_rows(path: Path | None = None) -> dict[str, list[dict]]:
    path = path or (ROOTCAUSE_DIR / "rounds.csv")
    rows_by_round: dict[str, list[dict]] = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for raw in reader:
            converted: dict[str, Any] = {}
            for k, v in raw.items():
                converted[k] = v if k in ("round_id", "date") else _coerce(v)
            rows_by_round.setdefault(raw["round_id"], []).append(converted)
    return rows_by_round


def list_parent_causes(
    concept_label: str,
    mode: OntologyMode = OntologyMode.FULL,
    ontology_variant: str | None = None,
) -> dict[str, Any]:
    graph = load_ontology(variant=ontology_variant)
    query = f"""
    PREFIX : <{ONT}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?ruleLabel ?causeLabel ?magnitude ?description ?causeMetric ?isMetricTyped
    WHERE {{
        ?rule a :CausalRule ;
              rdfs:label ?ruleLabel ;
              :hasCause ?cause ;
              :hasEffect ?effect ;
              :hasDescription ?description .
        ?effect rdfs:label ?effectLabel .
        ?cause rdfs:label ?causeLabel .
        FILTER (LCASE(STR(?effectLabel)) = LCASE("{concept_label}"))
        OPTIONAL {{ ?rule :hasExpectedMagnitude ?magnitude }}
        OPTIONAL {{ ?cause :measuredBy ?causeMetric }}
        OPTIONAL {{
            ?cause a :Metric .
            BIND(true AS ?isMetricTyped)
        }}
    }}
    """
    parents: list[dict[str, Any]] = []
    for row in graph.query(query):
        friendly = str(row.causeMetric) if row.causeMetric is not None else None
        metric_id = _FRIENDLY_TO_OPAQUE.get(friendly) if friendly else None
        is_metric_typed = row.isMetricTyped is not None

        parent: dict[str, Any] = {
            "cause_concept": str(row.causeLabel),
        }

        # Mode-dependent field selection.
        if mode in (
            OntologyMode.FULL,
            OntologyMode.NO_DESC_MAG,
            OntologyMode.NO_CLASS_MEASURED_BY,
        ):
            parent["rule"] = str(row.ruleLabel)

        if mode in (OntologyMode.FULL, OntologyMode.NO_CLASS_MEASURED_BY):
            parent["expected_magnitude"] = (
                str(row.magnitude) if row.magnitude is not None else None
            )
            parent["description"] = str(row.description)

        # metric_id handling
        if mode == OntologyMode.CONCEPTS_ONLY:
            pass  # never include metric_id
        elif mode == OntologyMode.NO_CLASS_MEASURED_BY:
            parent["metric_id"] = metric_id if is_metric_typed else None
        else:
            # FULL, NO_DESC_MAG, STRUCT_AND_METRIC_ID all include metric_id
            parent["metric_id"] = metric_id

        parents.append(parent)
    return {"effect_concept": concept_label, "parent_causes": parents}


def compare_metric_round(
    metric_id: str, round_a: str, round_b: str
) -> dict[str, Any]:
    if metric_id not in METRIC_ALIAS:
        return {
            "error": (
                f"unknown metric_id '{metric_id}'. Known ids: "
                f"{sorted(METRIC_ALIAS.keys())}"
            )
        }
    friendly = METRIC_ALIAS[metric_id]
    agg = _FRIENDLY_AGGREGATIONS[friendly]
    rows_by_round = _load_rounds_rows()
    if round_a not in rows_by_round or round_b not in rows_by_round:
        return {
            "error": (
                f"unknown round id. Known rounds: {sorted(rows_by_round.keys())}"
            )
        }
    value_a = agg(rows_by_round[round_a])
    value_b = agg(rows_by_round[round_b])
    delta_pct: float | None = None
    if value_a != 0:
        delta_pct = (value_b - value_a) / abs(value_a) * 100
    return {
        "metric_id": metric_id,
        "round_a": round_a,
        "round_b": round_b,
        "value_a": round(value_a, 3),
        "value_b": round(value_b, 3),
        "delta_abs": round(value_b - value_a, 3),
        "delta_pct": round(delta_pct, 2) if delta_pct is not None else None,
    }


def build_causal_payload(
    ontology_variant: str | None = None,
) -> list[dict[str, Any]]:
    """Return the full flat list of causal rules for push-format prompts.

    Same information that list_parent_causes(FULL) would return if called
    for every concept, but pre-computed and flattened so it can be embedded
    in a system prompt without any tool interaction. Each rule is resolved
    to opaque metric ids on both the cause and effect sides via
    :measuredBy (class-level bindings included).
    """
    graph = load_ontology(variant=ontology_variant)
    query = f"""
    PREFIX : <{ONT}>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?ruleLabel ?causeLabel ?effectLabel ?description ?magnitude
           ?causeMetric ?effectMetric
    WHERE {{
        ?rule a :CausalRule ;
              rdfs:label ?ruleLabel ;
              :hasCause ?cause ;
              :hasEffect ?effect ;
              :hasDescription ?description .
        ?cause rdfs:label ?causeLabel .
        ?effect rdfs:label ?effectLabel .
        OPTIONAL {{ ?rule :hasExpectedMagnitude ?magnitude }}
        OPTIONAL {{ ?cause :measuredBy ?causeMetric }}
        OPTIONAL {{ ?effect :measuredBy ?effectMetric }}
    }}
    ORDER BY ?effectLabel ?causeLabel
    """
    rules: list[dict[str, Any]] = []
    for row in graph.query(query):
        cause_friendly = str(row.causeMetric) if row.causeMetric is not None else None
        effect_friendly = (
            str(row.effectMetric) if row.effectMetric is not None else None
        )
        rules.append(
            {
                "cause_concept": str(row.causeLabel),
                "cause_metric_id": (
                    _FRIENDLY_TO_OPAQUE.get(cause_friendly) if cause_friendly else None
                ),
                "effect_concept": str(row.effectLabel),
                "effect_metric_id": (
                    _FRIENDLY_TO_OPAQUE.get(effect_friendly)
                    if effect_friendly
                    else None
                ),
                "rule_label": str(row.ruleLabel),
                "description": str(row.description),
                "expected_magnitude": (
                    str(row.magnitude) if row.magnitude is not None else None
                ),
            }
        )
    return rules
