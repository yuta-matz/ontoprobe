"""Progressive property ablation: 5 tiers × 20 VIP scenarios.

Tests which ontology property yields the biggest accuracy jump when
added incrementally. Tiers:

  T0 NONE                 — no list_parent_causes (baseline)
  T1 CONCEPTS_ONLY        — + parent concept labels
  T2 STRUCT_AND_METRIC_ID — + metric_id (measuredBy resolution)
  T3 NO_DESC_MAG          — + rdfs:label on rules
  T4 FULL                 — + hasDescription + hasExpectedMagnitude

Existing VIP results for T0 and T4 are reloaded from
``data/rootcause/vip_ablation_raw.json`` to save runtime; T1/T2/T3 are
executed fresh (60 new runs). Reports hit rate, 95% Wilson CI, and the
marginal lift of each added property.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from scipy.stats import binomtest

from ontoprobe.config import DATA_DIR
from ontoprobe.rootcause.agent import run_rootcause_agent
from ontoprobe.rootcause.data_gen import build_vip_focused_scenarios, save_scenarios
from ontoprobe.rootcause.eval import TraceStats, summarize_trace
from ontoprobe.rootcause.tools import OntologyMode

console = Console(width=130)
RESULTS_DIR = DATA_DIR / "rootcause"


@dataclass
class Tier:
    label: str
    mode: OntologyMode
    added_property: str


TIERS: list[Tier] = [
    Tier("T0 none", OntologyMode.NONE, "—"),
    Tier("T1 concepts", OntologyMode.CONCEPTS_ONLY, "+ parent concept labels"),
    Tier(
        "T2 +metric_id",
        OntologyMode.STRUCT_AND_METRIC_ID,
        "+ :measuredBy (metric_id)",
    ),
    Tier("T3 +rule labels", OntologyMode.NO_DESC_MAG, "+ rdfs:label on rules"),
    Tier("T4 full", OntologyMode.FULL, "+ :hasDescription + :hasExpectedMagnitude"),
]

# Tiers we already have results for on VIP 20 (from Phase 5).
REUSED_TIERS = {"T0 none": "M4 none", "T4 full": "M0 full"}


def _wilson_ci(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    res = binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
    return (float(res.low), float(res.high))


def _mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return float(binomtest(k, n, 0.5, alternative="two-sided").pvalue)


def _load_vip_baseline() -> dict[str, dict[str, dict]]:
    path = RESULTS_DIR / "vip_ablation_raw.json"
    with open(path) as f:
        return json.load(f)


def main() -> None:
    console.print(
        Panel(
            "[bold]Progressive VIP ablation — 5 tiers × 20 scenarios[/]\n"
            "[dim]Reuses T0/T4 from Phase 5; runs T1/T2/T3 fresh (60 new runs).[/]",
            expand=False,
        )
    )

    scenarios = build_vip_focused_scenarios()
    save_scenarios(scenarios)

    # Load reused tiers
    vip_baseline = _load_vip_baseline()
    all_results: dict[str, dict[str, TraceStats]] = {}
    for tier in TIERS:
        if tier.label in REUSED_TIERS:
            reuse_key = REUSED_TIERS[tier.label]
            raw = vip_baseline[reuse_key]
            all_results[tier.label] = {
                sid: TraceStats(
                    hit=data["hit"],
                    reported_concept=data["reported_concept"],
                    iterations=data["iterations"],
                    tool_calls=data["iterations"],  # best guess
                    compare_calls=data["compare_calls"],
                    list_parent_calls=data["list_parent_calls"],
                    queried_metrics=data.get("queried_metrics", []),
                    on_gt_path_queries=0,
                    on_any_ancestor_queries=0,
                    wrong_branch_queries=data["wrong_branch_queries"],
                    precision_gt_path=data["precision_gt_path"],
                    precision_any_ancestor=data["precision_any_ancestor"],
                    stopped_reason="loaded",
                    cost_usd=data["cost_usd"],
                )
                for sid, data in raw.items()
            }
            console.print(
                f"[dim]Loaded {tier.label} from Phase 5 "
                f"({reuse_key}): {sum(1 for s in all_results[tier.label].values() if s.hit)}/"
                f"{len(all_results[tier.label])} hits[/]"
            )
            continue

        console.print(Panel(f"[bold]{tier.label}[/] — {tier.added_property}", border_style="yellow"))
        tier_results: dict[str, TraceStats] = {}
        for s in scenarios:
            trace = run_rootcause_agent(
                anomaly_metric_id="m_101",
                round_a=s.baseline.round_id,
                round_b=s.anomaly.round_id,
                ontology_mode=tier.mode,
            )
            stats = summarize_trace(trace, "Revenue", "VIP Customer")
            tier_results[s.scenario_id] = stats
            mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
            console.print(
                f"  {s.scenario_id:14} shock→{s.anomaly.shocked_to:<5} "
                f"seed={s.seed:3d}  {mark}"
            )
        all_results[tier.label] = tier_results

    # Persist
    out_path = RESULTS_DIR / "progressive_vip_ablation_raw.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                tier_label: {
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
                    for sid, s in tier_results.items()
                }
                for tier_label, tier_results in all_results.items()
            },
            f,
            indent=2,
        )
    console.print(f"\n[dim]Raw results → {out_path}[/]")

    # ---- Tier ladder ----
    console.print()
    ladder = Table(title="\nProgressive tier ladder (N=20 VIP scenarios)", show_lines=True)
    ladder.add_column("Tier")
    ladder.add_column("Added property")
    ladder.add_column("Hit rate (95% CI)", justify="right")
    ladder.add_column("Marginal Δ pp", justify="right")
    ladder.add_column("p (McNemar vs prev)", justify="right")

    prev_hits: int | None = None
    prev_tier_label: str | None = None
    for tier in TIERS:
        results = all_results[tier.label]
        n = len(results)
        hits = sum(1 for s in results.values() if s.hit)
        lo, hi = _wilson_ci(hits, n)
        hit_str = (
            f"{hits}/{n} = {hits / n * 100:.0f}% [{lo * 100:.0f}%, {hi * 100:.0f}%]"
        )

        marginal = "—"
        p_str = "—"
        if prev_hits is not None and prev_tier_label is not None:
            marginal_pp = (hits - prev_hits) / n * 100
            marginal = f"{marginal_pp:+.0f}"
            prev_results = all_results[prev_tier_label]
            b = sum(
                1 for sid in results if results[sid].hit and not prev_results[sid].hit
            )
            c = sum(
                1 for sid in results if (not results[sid].hit) and prev_results[sid].hit
            )
            p = _mcnemar_exact(b, c)
            p_str = f"{p:.3f}"
            if p < 0.05:
                p_str = f"[bold green]{p_str}[/]"
        ladder.add_row(tier.label, tier.added_property, hit_str, marginal, p_str)
        prev_hits = hits
        prev_tier_label = tier.label
    console.print(ladder)

    # ---- Per-scenario progression matrix ----
    mat = Table(title="\nPer-scenario hit progression", show_lines=False)
    mat.add_column("Scenario")
    mat.add_column("Shock")
    mat.add_column("Seed", justify="right")
    for tier in TIERS:
        mat.add_column(tier.label.split()[0], justify="center")
    for s in scenarios:
        row = [s.scenario_id, f"{s.anomaly.shocked_to}", str(s.seed)]
        for tier in TIERS:
            hit = all_results[tier.label][s.scenario_id].hit
            row.append("[green]✓[/]" if hit else "[red]✗[/]")
        mat.add_row(*row)
    console.print(mat)

    # ---- Headline ----
    hits_t0 = sum(1 for s in all_results["T0 none"].values() if s.hit)
    hits_t4 = sum(1 for s in all_results["T4 full"].values() if s.hit)
    console.print(
        Panel(
            f"[bold]Baseline → full: {hits_t0}/20 → {hits_t4}/20[/] "
            f"(+{(hits_t4 - hits_t0) / 20 * 100:.0f} pp total)",
            title="Total lift",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
