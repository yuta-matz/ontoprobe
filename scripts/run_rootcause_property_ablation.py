"""Property-level ablation: which ontology properties carry the signal?

Runs the same 3 scenarios under 5 conditions that progressively strip
properties off the ontology layer:

  M0  FULL             — structure + class-level measuredBy + rule label
                         + description + expected magnitude
  M1  NO_DESC_MAG      — drop description and expected_magnitude, keep
                         structure + metric_id + rule label
  M2  NO_CLASS_MB      — drop metric_id on class-typed parents
                         (DiscountCampaign, VIPCustomer, ...), keep
                         description/magnitude/rule label
  M3  CONCEPTS_ONLY    — return cause concept labels only (no metric_id,
                         no rule label, no description, no magnitude)
  M4  NONE             — list_parent_causes removed entirely (baseline)

For each mode we measure hit rate, branch precision, step count, and
wrong-branch queries, then print the mode table side-by-side. The point
is to see which property, once stripped, causes the collapse — that's
the load-bearing one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ontoprobe.rootcause.agent import run_rootcause_agent
from ontoprobe.rootcause.data_gen import build_scenarios, save_scenarios
from ontoprobe.rootcause.eval import TraceStats, summarize_trace
from ontoprobe.rootcause.tools import OntologyMode

console = Console(width=130)


@dataclass
class AnomalyPrime:
    scenario_id: str
    anomaly_metric_id: str
    anomaly_concept: str


ANOMALY_PRIMES: list[AnomalyPrime] = [
    AnomalyPrime("S1", "m_103", "Order Volume"),
    AnomalyPrime("S2", "m_101", "Revenue"),
    AnomalyPrime("S3", "m_107", "Seasonal Revenue"),
]


MODES: list[tuple[str, OntologyMode, str]] = [
    ("M0 full", OntologyMode.FULL, "Structure + class-MB + rule label + desc + magnitude"),
    ("M1 −desc,mag", OntologyMode.NO_DESC_MAG, "Drop description and expected_magnitude"),
    ("M2 −class-MB", OntologyMode.NO_CLASS_MEASURED_BY, "Drop metric_id on class-typed parents"),
    ("M3 concepts only", OntologyMode.CONCEPTS_ONLY, "Concept labels only — no metric_id, no rule label, no desc, no magnitude"),
    ("M4 none", OntologyMode.NONE, "list_parent_causes removed entirely"),
]


def _fmt_precision(p: float | None) -> str:
    return "—" if p is None else f"{p * 100:.0f}%"


def _aggregate(stats: Iterable[TraceStats]) -> dict[str, float]:
    s_list = list(stats)
    n = len(s_list)
    precs_gt = [s.precision_gt_path for s in s_list if s.precision_gt_path is not None]
    precs_anc = [
        s.precision_any_ancestor for s in s_list if s.precision_any_ancestor is not None
    ]
    return {
        "hit_rate": sum(1 for s in s_list if s.hit) / n,
        "avg_steps": sum(s.iterations for s in s_list) / n,
        "avg_compare": sum(s.compare_calls for s in s_list) / n,
        "avg_list_parent": sum(s.list_parent_calls for s in s_list) / n,
        "avg_prec_gt": sum(precs_gt) / len(precs_gt) if precs_gt else 0.0,
        "avg_prec_anc": sum(precs_anc) / len(precs_anc) if precs_anc else 0.0,
        "avg_wrong": sum(s.wrong_branch_queries for s in s_list) / n,
        "total_cost": sum(s.cost_usd for s in s_list),
    }


def main() -> None:
    console.print(
        Panel(
            "[bold]Property-level ablation (5 modes × 3 scenarios)[/]\n"
            "[dim]Same data, same opaque metric ids, same system prompt structure; only the list_parent_causes output differs.[/]",
            expand=False,
        )
    )

    scenarios = build_scenarios()
    save_scenarios(scenarios)
    scenario_map = {s.scenario_id: s for s in scenarios}

    # results[mode_label][scenario_id] = TraceStats
    results: dict[str, dict[str, TraceStats]] = {m[0]: {} for m in MODES}

    for label, mode, description in MODES:
        console.print(
            Panel(
                f"[bold]{label}[/] — {description}",
                border_style="yellow",
            )
        )
        for prime in ANOMALY_PRIMES:
            scenario = scenario_map[prime.scenario_id]
            gt_concept = scenario.anomaly.shocked_concept
            console.print(
                f"  [dim]scenario {prime.scenario_id} "
                f"(anomaly={prime.anomaly_metric_id}, GT={gt_concept})[/]"
            )
            trace = run_rootcause_agent(
                anomaly_metric_id=prime.anomaly_metric_id,
                round_a=scenario.baseline.round_id,
                round_b=scenario.anomaly.round_id,
                ontology_mode=mode,
            )
            stats = summarize_trace(trace, prime.anomaly_concept, gt_concept)
            results[label][prime.scenario_id] = stats
            hit_mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
            console.print(
                f"    → {hit_mark} reported='{stats.reported_concept[:70]}' "
                f"steps={stats.iterations} wrong={stats.wrong_branch_queries}"
            )

    # ---- Per-mode aggregate table ----
    console.print()
    agg_table = Table(title="\nMode aggregates (avg over 3 scenarios)", show_lines=True)
    agg_table.add_column("Mode")
    agg_table.add_column("Hit", justify="right")
    agg_table.add_column("Steps", justify="right")
    agg_table.add_column("Cmp", justify="right")
    agg_table.add_column("LP", justify="right")
    agg_table.add_column("Prec(GT)", justify="right")
    agg_table.add_column("Prec(Anc)", justify="right")
    agg_table.add_column("Wrong", justify="right")
    agg_table.add_column("$", justify="right")

    for label, _, _ in MODES:
        agg = _aggregate(results[label].values())
        agg_table.add_row(
            label,
            f"{agg['hit_rate'] * 100:.0f}%",
            f"{agg['avg_steps']:.1f}",
            f"{agg['avg_compare']:.1f}",
            f"{agg['avg_list_parent']:.1f}",
            f"{agg['avg_prec_gt'] * 100:.0f}%",
            f"{agg['avg_prec_anc'] * 100:.0f}%",
            f"{agg['avg_wrong']:.1f}",
            f"${agg['total_cost']:.3f}",
        )
    console.print(agg_table)

    # ---- Per-scenario hit matrix ----
    hit_table = Table(title="\nHit matrix (mode × scenario)", show_lines=True)
    hit_table.add_column("Mode")
    for prime in ANOMALY_PRIMES:
        hit_table.add_column(
            f"{prime.scenario_id}\n{scenario_map[prime.scenario_id].anomaly.shocked_concept}",
            justify="center",
        )
    for label, _, _ in MODES:
        row = [label]
        for prime in ANOMALY_PRIMES:
            s = results[label][prime.scenario_id]
            mark = "[green]✓[/]" if s.hit else "[red]✗[/]"
            row.append(mark)
        hit_table.add_row(*row)
    console.print(hit_table)

    # ---- Per-scenario precision matrix ----
    prec_table = Table(
        title="\nPrecision (GT-path) matrix", show_lines=True
    )
    prec_table.add_column("Mode")
    for prime in ANOMALY_PRIMES:
        prec_table.add_column(prime.scenario_id, justify="right")
    for label, _, _ in MODES:
        row = [label]
        for prime in ANOMALY_PRIMES:
            s = results[label][prime.scenario_id]
            row.append(_fmt_precision(s.precision_gt_path))
        prec_table.add_row(*row)
    console.print(prec_table)


if __name__ == "__main__":
    main()
