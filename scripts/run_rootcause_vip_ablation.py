"""Focused VIP ablation: N=20, M0 vs M4.

Tests the targeted hypothesis: when the root cause is a class-typed
abstract concept (VIPCustomer) that requires ontology-mediated metric
resolution to trace, does the full ontology beat the no-ontology
baseline?

20 VIP-only scenarios × 2 modes = 40 runs. Different RNG seeds per
scenario vary the distractor pattern so the comparison is not
dominated by a single lucky round. McNemar paired test + Wilson CI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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

MODES: list[tuple[str, OntologyMode]] = [
    ("M0 full", OntologyMode.FULL),
    ("M4 none", OntologyMode.NONE),
]


def _wilson_ci(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    res = binomtest(k, n).proportion_ci(confidence_level=1 - alpha, method="wilson")
    return (float(res.low), float(res.high))


def _mcnemar_exact(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return float(binomtest(k, n, 0.5, alternative="two-sided").pvalue)


def main() -> None:
    console.print(
        Panel(
            "[bold]VIP-focused ablation — 20 scenarios × 2 modes = 40 runs[/]\n"
            "[dim]All scenarios: VIP Customer ground truth, 4 magnitudes × 5 seeds. Priming on m_101 (Revenue).[/]",
            expand=False,
        )
    )

    scenarios = build_vip_focused_scenarios()
    save_scenarios(scenarios)
    console.print(f"Generated {len(scenarios)} VIP scenarios\n")

    all_results: dict[str, dict[str, TraceStats]] = {}
    for label, mode in MODES:
        console.print(Panel(f"[bold]{label}[/]", border_style="yellow"))
        results: dict[str, TraceStats] = {}
        for scenario in scenarios:
            sid = scenario.scenario_id
            console.print(
                f"  [dim]{sid} "
                f"(shock=vip→{scenario.anomaly.shocked_to}, seed={scenario.seed})[/]"
            )
            trace = run_rootcause_agent(
                anomaly_metric_id="m_101",
                round_a=scenario.baseline.round_id,
                round_b=scenario.anomaly.round_id,
                ontology_mode=mode,
            )
            stats = summarize_trace(trace, "Revenue", "VIP Customer")
            results[sid] = stats
            mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
            console.print(
                f"    → {mark} steps={stats.iterations} wrong={stats.wrong_branch_queries}"
            )
        all_results[label] = results

    # Persist raw results
    out_path = RESULTS_DIR / "vip_ablation_raw.json"
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
    console.print(f"\n[dim]Raw results → {out_path}[/]")

    # Hit matrix
    matrix = Table(title="\nHit matrix (M0 vs M4)", show_lines=False)
    matrix.add_column("Scenario")
    matrix.add_column("Shock")
    matrix.add_column("Seed", justify="right")
    matrix.add_column("M0", justify="center")
    matrix.add_column("M4", justify="center")
    matrix.add_column("Outcome")
    for s in scenarios:
        sid = s.scenario_id
        m0 = all_results["M0 full"][sid].hit
        m4 = all_results["M4 none"][sid].hit
        outcome = ""
        if m0 and not m4:
            outcome = "[green]M0 wins[/]"
        elif m4 and not m0:
            outcome = "[red]M4 wins[/]"
        elif m0 and m4:
            outcome = "both ✓"
        else:
            outcome = "[dim]both ✗[/]"
        matrix.add_row(
            sid,
            f"{s.anomaly.shocked_to}",
            str(s.seed),
            "[green]✓[/]" if m0 else "[red]✗[/]",
            "[green]✓[/]" if m4 else "[red]✗[/]",
            outcome,
        )
    console.print(matrix)

    # Aggregate
    m0_hits = sum(1 for s in all_results["M0 full"].values() if s.hit)
    m4_hits = sum(1 for s in all_results["M4 none"].values() if s.hit)
    n = len(scenarios)
    m0_lo, m0_hi = _wilson_ci(m0_hits, n)
    m4_lo, m4_hi = _wilson_ci(m4_hits, n)

    b = sum(
        1
        for sid in all_results["M0 full"]
        if all_results["M0 full"][sid].hit and not all_results["M4 none"][sid].hit
    )
    c = sum(
        1
        for sid in all_results["M0 full"]
        if (not all_results["M0 full"][sid].hit) and all_results["M4 none"][sid].hit
    )
    p = _mcnemar_exact(b, c)

    agg = Table(title="\nAggregate (N=20 VIP scenarios)", show_lines=True)
    agg.add_column("Mode")
    agg.add_column("Hit rate (95% CI)", justify="right")
    agg.add_column("Avg steps", justify="right")
    agg.add_column("Avg wrong", justify="right")
    agg.add_column("Avg prec(GT)", justify="right")
    agg.add_column("Cost", justify="right")
    for label, _ in MODES:
        stats = list(all_results[label].values())
        hits = sum(1 for s in stats if s.hit)
        lo, hi = _wilson_ci(hits, n)
        precs = [s.precision_gt_path for s in stats if s.precision_gt_path is not None]
        agg.add_row(
            label,
            f"{hits}/{n} = {hits / n * 100:.0f}% [{lo * 100:.0f}%, {hi * 100:.0f}%]",
            f"{sum(s.iterations for s in stats) / n:.1f}",
            f"{sum(s.wrong_branch_queries for s in stats) / n:.1f}",
            f"{(sum(precs) / len(precs)) * 100:.0f}%" if precs else "—",
            f"${sum(s.cost_usd for s in stats):.2f}",
        )
    console.print(agg)

    test_table = Table(title="\nMcNemar paired test (M0 vs M4)", show_lines=True)
    test_table.add_column("b (M0 hits, M4 misses)", justify="right")
    test_table.add_column("c (M0 misses, M4 hits)", justify="right")
    test_table.add_column("p (exact, two-sided)", justify="right")
    test_table.add_column("Interp")
    interp = "M0 > M4" if p < 0.05 and b > c else (
        "M4 > M0" if p < 0.05 and c > b else "No significant difference"
    )
    test_table.add_row(str(b), str(c), f"{p:.4f}", interp)
    console.print(test_table)

    console.print(
        Panel(
            f"[bold]Headline:[/] M0 = {m0_hits}/{n} "
            f"({m0_hits / n * 100:.0f}%, CI [{m0_lo * 100:.0f}%, {m0_hi * 100:.0f}%])   "
            f"M4 = {m4_hits}/{n} "
            f"({m4_hits / n * 100:.0f}%, CI [{m4_lo * 100:.0f}%, {m4_hi * 100:.0f}%])   "
            f"Δ = {(m0_hits - m4_hits) / n * 100:+.0f} pp   "
            f"McNemar p = {p:.4f}",
            title="Effect size",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
