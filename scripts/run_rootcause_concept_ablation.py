"""Three-concept focused ablation: VIP, Discount, Seasonal, each N=20.

Runs the VIP-focused builder against Discount- and Seasonal-focused
builders of the same shape (4 magnitudes × 5 seeds, all class-typed
ground truth). Compares M0 full vs M4 none on each concept, then
produces a cross-concept effect-size table.

VIP results are regenerated here (not loaded from disk) so all three
concepts use the exact same code path and are comparable. Raw results
are persisted to data/rootcause/concept_ablation_raw.json.

60 scenarios × 2 modes = 120 runs total, ~60 min, ~$10.
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
from ontoprobe.rootcause.data_gen import (
    Scenario,
    build_discount_focused_scenarios,
    build_seasonal_focused_scenarios,
    build_vip_focused_scenarios,
    save_scenarios,
)
from ontoprobe.rootcause.eval import TraceStats, summarize_trace
from ontoprobe.rootcause.tools import OntologyMode

console = Console(width=130)
RESULTS_DIR = DATA_DIR / "rootcause"


@dataclass
class ConceptTest:
    label: str
    builder: Callable[[], list[Scenario]]
    anomaly_metric_id: str
    anomaly_concept: str
    ground_truth_concept: str


CONCEPTS: list[ConceptTest] = [
    ConceptTest(
        label="VIP Customer",
        builder=build_vip_focused_scenarios,
        anomaly_metric_id="m_101",
        anomaly_concept="Revenue",
        ground_truth_concept="VIP Customer",
    ),
    ConceptTest(
        label="Discount Campaign",
        builder=build_discount_focused_scenarios,
        anomaly_metric_id="m_101",
        anomaly_concept="Revenue",
        ground_truth_concept="Discount Campaign",
    ),
    ConceptTest(
        label="Seasonal Product",
        builder=build_seasonal_focused_scenarios,
        anomaly_metric_id="m_107",
        anomaly_concept="Seasonal Revenue",
        ground_truth_concept="Seasonal Product",
    ),
]


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


def _run_concept(ct: ConceptTest) -> dict[str, dict[str, TraceStats]]:
    console.print(
        Panel(
            f"[bold]{ct.label}[/] — 20 scenarios, M0 vs M4",
            border_style="cyan",
        )
    )
    scenarios = ct.builder()
    save_scenarios(scenarios)

    results: dict[str, dict[str, TraceStats]] = {}
    for label, mode in MODES:
        console.print(f"[bold blue]  Running {label}...[/]")
        mode_results: dict[str, TraceStats] = {}
        for s in scenarios:
            trace = run_rootcause_agent(
                anomaly_metric_id=ct.anomaly_metric_id,
                round_a=s.baseline.round_id,
                round_b=s.anomaly.round_id,
                ontology_mode=mode,
            )
            stats = summarize_trace(trace, ct.anomaly_concept, ct.ground_truth_concept)
            mode_results[s.scenario_id] = stats
            mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
            console.print(
                f"    {s.scenario_id:14} shock→{s.anomaly.shocked_to:<5} "
                f"seed={s.seed:3d}  {mark}"
            )
        results[label] = mode_results
    return results


def main() -> None:
    console.print(
        Panel(
            "[bold]3-concept focused ablation — 60 scenarios × 2 modes = 120 runs[/]\n"
            "[dim]Parallel N=20 for VIP / Discount / Seasonal, each with its class-typed GT concept.[/]",
            expand=False,
        )
    )

    all_results: dict[str, dict[str, dict[str, TraceStats]]] = {}
    for ct in CONCEPTS:
        all_results[ct.label] = _run_concept(ct)

    # Persist raw
    out_path = RESULTS_DIR / "concept_ablation_raw.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                concept_label: {
                    mode_label: {
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
                    for mode_label, mode_results in concept_results.items()
                }
                for concept_label, concept_results in all_results.items()
            },
            f,
            indent=2,
        )
    console.print(f"\n[dim]Raw results → {out_path}[/]")

    # ---- Per-concept summary ----
    console.print()
    summary_table = Table(
        title="\nCross-concept effect size (N=20 per concept)", show_lines=True
    )
    summary_table.add_column("Concept")
    summary_table.add_column("M0 hit (95% CI)", justify="right")
    summary_table.add_column("M4 hit (95% CI)", justify="right")
    summary_table.add_column("Δ pp", justify="right")
    summary_table.add_column("b", justify="right")
    summary_table.add_column("c", justify="right")
    summary_table.add_column("McNemar p", justify="right")
    summary_table.add_column("Signif?", justify="center")

    totals: dict[str, dict[str, int]] = {"M0 full": {"hit": 0, "n": 0}, "M4 none": {"hit": 0, "n": 0}}
    global_b = 0
    global_c = 0

    for ct in CONCEPTS:
        m0 = all_results[ct.label]["M0 full"]
        m4 = all_results[ct.label]["M4 none"]
        m0_hits = sum(1 for s in m0.values() if s.hit)
        m4_hits = sum(1 for s in m4.values() if s.hit)
        n = len(m0)
        lo0, hi0 = _wilson_ci(m0_hits, n)
        lo4, hi4 = _wilson_ci(m4_hits, n)

        b = sum(1 for sid in m0 if m0[sid].hit and not m4[sid].hit)
        c = sum(1 for sid in m0 if (not m0[sid].hit) and m4[sid].hit)
        p = _mcnemar_exact(b, c)

        totals["M0 full"]["hit"] += m0_hits
        totals["M0 full"]["n"] += n
        totals["M4 none"]["hit"] += m4_hits
        totals["M4 none"]["n"] += n
        global_b += b
        global_c += c

        signif = "[green]✓[/]" if p < 0.05 else "[dim]—[/]"
        delta_pp = (m0_hits - m4_hits) / n * 100
        summary_table.add_row(
            ct.label,
            f"{m0_hits}/{n} = {m0_hits / n * 100:.0f}% [{lo0 * 100:.0f}%, {hi0 * 100:.0f}%]",
            f"{m4_hits}/{n} = {m4_hits / n * 100:.0f}% [{lo4 * 100:.0f}%, {hi4 * 100:.0f}%]",
            f"{delta_pp:+.0f}",
            str(b),
            str(c),
            f"{p:.4f}",
            signif,
        )

    # Pooled row
    m0_total_h = totals["M0 full"]["hit"]
    m4_total_h = totals["M4 none"]["hit"]
    n_total = totals["M0 full"]["n"]
    lo0_t, hi0_t = _wilson_ci(m0_total_h, n_total)
    lo4_t, hi4_t = _wilson_ci(m4_total_h, n_total)
    p_total = _mcnemar_exact(global_b, global_c)
    delta_total = (m0_total_h - m4_total_h) / n_total * 100
    summary_table.add_row(
        "[bold]POOLED[/]",
        f"{m0_total_h}/{n_total} = {m0_total_h / n_total * 100:.0f}% [{lo0_t * 100:.0f}%, {hi0_t * 100:.0f}%]",
        f"{m4_total_h}/{n_total} = {m4_total_h / n_total * 100:.0f}% [{lo4_t * 100:.0f}%, {hi4_t * 100:.0f}%]",
        f"{delta_total:+.0f}",
        str(global_b),
        str(global_c),
        f"{p_total:.4f}",
        "[green]✓[/]" if p_total < 0.05 else "[dim]—[/]",
        style="bold",
    )
    console.print(summary_table)

    # ---- Per-scenario detailed hit matrix (compact) ----
    console.print()
    for ct in CONCEPTS:
        mat = Table(title=f"\n{ct.label} — hit matrix", show_lines=False)
        mat.add_column("Scenario")
        mat.add_column("Shock")
        mat.add_column("Seed", justify="right")
        mat.add_column("M0", justify="center")
        mat.add_column("M4", justify="center")
        scenarios = ct.builder()
        m0 = all_results[ct.label]["M0 full"]
        m4 = all_results[ct.label]["M4 none"]
        for s in scenarios:
            mat.add_row(
                s.scenario_id,
                f"{s.anomaly.shocked_to}",
                str(s.seed),
                "[green]✓[/]" if m0[s.scenario_id].hit else "[red]✗[/]",
                "[green]✓[/]" if m4[s.scenario_id].hit else "[red]✗[/]",
            )
        console.print(mat)


if __name__ == "__main__":
    main()
