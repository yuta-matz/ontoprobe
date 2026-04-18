"""Statistical ablation: 15 scenarios × 3 ontology modes.

Scenarios: 3 cause concepts (DiscountCampaign, VIPCustomer, SeasonalProduct)
at 5 magnitudes each. Modes: M0 full ontology, M3 concepts-only (no
metric_id binding), M4 no ontology at all. 45 runs total.

Reports:
  - Per-mode hit rate with Wilson 95% confidence interval
  - Per-scenario hit matrix (mode × scenario)
  - McNemar paired test: M0 vs M4 and M0 vs M3
  - Per-concept hit rate breakdown
  - Precision metrics (GT path and any-ancestor)
  - Aggregate step count, cost, wrong-branch queries

Requires scipy for the Wilson CI and McNemar exact test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from scipy.stats import binomtest

from ontoprobe.config import DATA_DIR
from ontoprobe.rootcause.agent import run_rootcause_agent
from ontoprobe.rootcause.data_gen import build_scenarios, save_scenarios
from ontoprobe.rootcause.eval import TraceStats, summarize_trace
from ontoprobe.rootcause.tools import METRIC_ALIAS, OntologyMode

console = Console(width=130)
RESULTS_DIR = DATA_DIR / "rootcause"


@dataclass
class AnomalyPrime:
    scenario_id: str
    anomaly_metric_id: str
    anomaly_concept: str


# Map ground-truth concept to the anomaly metric the orchestrator primes on.
# Revenue is the natural observable for discount / VIP shocks.
# Seasonal revenue is the natural observable for seasonal shocks.
CONCEPT_TO_PRIME: dict[str, tuple[str, str]] = {
    "Discount Campaign": ("m_101", "Revenue"),
    "VIP Customer": ("m_101", "Revenue"),
    "Seasonal Product": ("m_107", "Seasonal Revenue"),
}


MODES: list[tuple[str, OntologyMode, str]] = [
    ("M0 full", OntologyMode.FULL, "Full ontology"),
    (
        "M3 concepts only",
        OntologyMode.CONCEPTS_ONLY,
        "Parent concept labels only — no metric_id resolution",
    ),
    ("M4 none", OntologyMode.NONE, "list_parent_causes removed"),
]


def _wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    res = binomtest(k, n).proportion_ci(confidence_level=1 - alpha, method="wilson")
    return (float(res.low), float(res.high))


def _mcnemar_exact(b: int, c: int) -> float:
    """Two-sided McNemar exact test via binomial distribution.

    Given discordant pairs: b = M0-wins (M0 hit, other miss),
    c = Other-wins (M0 miss, other hit). Under H0 they are symmetric
    binomial(b+c, 0.5).
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return float(binomtest(k, n, 0.5, alternative="two-sided").pvalue)


def _run_mode(
    label: str,
    mode: OntologyMode,
    scenarios,
    scenario_map: dict,
    primes: dict[str, AnomalyPrime],
) -> dict[str, TraceStats]:
    results: dict[str, TraceStats] = {}
    for scenario in scenarios:
        sid = scenario.scenario_id
        prime = primes[sid]
        gt_concept = scenario.anomaly.shocked_concept
        console.print(
            f"  [dim]{sid} "
            f"(anomaly={prime.anomaly_metric_id}, GT={gt_concept}, "
            f"lever={scenario.anomaly.shocked_lever}: "
            f"{scenario.anomaly.shocked_from}→{scenario.anomaly.shocked_to})[/]"
        )
        trace = run_rootcause_agent(
            anomaly_metric_id=prime.anomaly_metric_id,
            round_a=scenario.baseline.round_id,
            round_b=scenario.anomaly.round_id,
            ontology_mode=mode,
        )
        stats = summarize_trace(trace, prime.anomaly_concept, gt_concept)
        results[sid] = stats
        mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
        console.print(
            f"    → {mark} steps={stats.iterations} wrong={stats.wrong_branch_queries} "
            f"prec_gt={stats.precision_gt_path if stats.precision_gt_path is not None else '—'}"
        )
    return results


def _aggregate(stats: Iterable[TraceStats]) -> dict[str, float]:
    s_list = list(stats)
    n = len(s_list)
    precs_gt = [s.precision_gt_path for s in s_list if s.precision_gt_path is not None]
    precs_anc = [
        s.precision_any_ancestor for s in s_list if s.precision_any_ancestor is not None
    ]
    hits = sum(1 for s in s_list if s.hit)
    lo, hi = _wilson_ci(hits, n)
    return {
        "hits": hits,
        "n": n,
        "hit_rate": hits / n,
        "ci_lo": lo,
        "ci_hi": hi,
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
            "[bold]Statistical root-cause ablation — 15 scenarios × 3 modes (45 runs)[/]\n"
            "[dim]3 cause concepts × 5 magnitudes each, paired across modes.[/]",
            expand=False,
        )
    )

    scenarios = build_scenarios()
    save_scenarios(scenarios)
    scenario_map = {s.scenario_id: s for s in scenarios}

    primes: dict[str, AnomalyPrime] = {}
    for s in scenarios:
        metric_id, concept = CONCEPT_TO_PRIME[s.anomaly.shocked_concept]
        primes[s.scenario_id] = AnomalyPrime(
            scenario_id=s.scenario_id,
            anomaly_metric_id=metric_id,
            anomaly_concept=concept,
        )

    all_results: dict[str, dict[str, TraceStats]] = {}
    for label, mode, description in MODES:
        console.print(
            Panel(f"[bold]{label}[/] — {description}", border_style="yellow")
        )
        all_results[label] = _run_mode(label, mode, scenarios, scenario_map, primes)

    # Persist raw results to disk for later analysis
    out_path = RESULTS_DIR / "stat_ablation_raw.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                label: {
                    sid: {
                        "hit": s.hit,
                        "reported_concept": s.reported_concept,
                        "iterations": s.iterations,
                        "compare_calls": s.compare_calls,
                        "list_parent_calls": s.list_parent_calls,
                        "queried_metrics": s.queried_metrics,
                        "precision_gt_path": s.precision_gt_path,
                        "precision_any_ancestor": s.precision_any_ancestor,
                        "wrong_branch_queries": s.wrong_branch_queries,
                        "cost_usd": s.cost_usd,
                    }
                    for sid, s in mode_results.items()
                }
                for label, mode_results in all_results.items()
            },
            f,
            indent=2,
        )
    console.print(f"\n[dim]Raw results saved to {out_path}[/]")

    # ---- Per-mode aggregate with Wilson CI ----
    console.print()
    agg_table = Table(
        title="\nMode aggregates (N=15 per mode)", show_lines=True
    )
    agg_table.add_column("Mode")
    agg_table.add_column("Hit rate (95% CI)", justify="right")
    agg_table.add_column("Steps", justify="right")
    agg_table.add_column("Cmp", justify="right")
    agg_table.add_column("LP", justify="right")
    agg_table.add_column("Prec(GT)", justify="right")
    agg_table.add_column("Prec(Anc)", justify="right")
    agg_table.add_column("Wrong", justify="right")
    agg_table.add_column("$", justify="right")

    aggregates: dict[str, dict] = {}
    for label, _, _ in MODES:
        agg = _aggregate(all_results[label].values())
        aggregates[label] = agg
        hit_str = (
            f"{agg['hits']}/{agg['n']} "
            f"= {agg['hit_rate'] * 100:.0f}% "
            f"[{agg['ci_lo'] * 100:.0f}%, {agg['ci_hi'] * 100:.0f}%]"
        )
        agg_table.add_row(
            label,
            hit_str,
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
    hit_table.add_column("Scenario", style="bold")
    hit_table.add_column("Shock")
    for label, _, _ in MODES:
        hit_table.add_column(label, justify="center")
    for scenario in scenarios:
        sid = scenario.scenario_id
        shock = (
            f"{scenario.anomaly.shocked_lever}: "
            f"{scenario.anomaly.shocked_from}→{scenario.anomaly.shocked_to}"
        )
        row = [sid, shock]
        for label, _, _ in MODES:
            s = all_results[label][sid]
            mark = "[green]✓[/]" if s.hit else "[red]✗[/]"
            row.append(mark)
        hit_table.add_row(*row)
    console.print(hit_table)

    # ---- Per-concept hit breakdown ----
    concept_table = Table(
        title="\nHit rate by ground-truth concept", show_lines=True
    )
    concept_table.add_column("Concept")
    concept_table.add_column("N", justify="right")
    for label, _, _ in MODES:
        concept_table.add_column(label, justify="right")
    concepts_seen = sorted({s.anomaly.shocked_concept for s in scenarios})
    for concept in concepts_seen:
        scenario_ids_for_concept = [
            s.scenario_id for s in scenarios if s.anomaly.shocked_concept == concept
        ]
        row = [concept, str(len(scenario_ids_for_concept))]
        for label, _, _ in MODES:
            hits = sum(
                1 for sid in scenario_ids_for_concept if all_results[label][sid].hit
            )
            n = len(scenario_ids_for_concept)
            row.append(f"{hits}/{n} = {hits / n * 100:.0f}%")
        concept_table.add_row(*row)
    console.print(concept_table)

    # ---- McNemar paired test ----
    console.print()
    mcnemar_table = Table(
        title="\nMcNemar paired test (M0 vs other)", show_lines=True
    )
    mcnemar_table.add_column("Pair")
    mcnemar_table.add_column("M0-only hits (b)", justify="right")
    mcnemar_table.add_column("Other-only hits (c)", justify="right")
    mcnemar_table.add_column("p (two-sided, exact)", justify="right")
    mcnemar_table.add_column("Interp", justify="left")

    m0_results = all_results["M0 full"]
    for label, _, _ in MODES:
        if label == "M0 full":
            continue
        other = all_results[label]
        b = sum(
            1
            for sid in m0_results
            if m0_results[sid].hit and not other[sid].hit
        )
        c = sum(
            1
            for sid in m0_results
            if (not m0_results[sid].hit) and other[sid].hit
        )
        p = _mcnemar_exact(b, c)
        interp = "M0 > other" if p < 0.05 and b > c else (
            "Other > M0" if p < 0.05 and c > b else "No significant difference"
        )
        mcnemar_table.add_row(
            f"M0 vs {label}",
            str(b),
            str(c),
            f"{p:.4f}",
            interp,
        )
    console.print(mcnemar_table)

    # ---- Summary headline ----
    m0 = aggregates["M0 full"]
    m4 = aggregates["M4 none"]
    diff = m0["hit_rate"] - m4["hit_rate"]
    console.print()
    console.print(
        Panel(
            f"[bold]Headline:[/] "
            f"M0 full = {m0['hits']}/{m0['n']} ({m0['hit_rate'] * 100:.0f}%, "
            f"95% CI [{m0['ci_lo'] * 100:.0f}%, {m0['ci_hi'] * 100:.0f}%])\n"
            f"           M4 none = {m4['hits']}/{m4['n']} ({m4['hit_rate'] * 100:.0f}%, "
            f"95% CI [{m4['ci_lo'] * 100:.0f}%, {m4['ci_hi'] * 100:.0f}%])\n"
            f"           Δ = {diff * 100:+.0f} pp",
            title="Effect size",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
