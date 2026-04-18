"""Format-comparison ablation for the root-cause loop.

Tests whether the Phase 6 effect (Δ=+38pp, p<0.0001) is ontology-format
specific or information specific. Same 60 scenarios (3 class-typed
concepts × 20 each), same LLM, same causal information content; only
the DELIVERY FORMAT of that information differs across 4 conditions:

  F_ontology  — existing M0 full: pull via SPARQL tool (list_parent_causes)
  F_json_push — flat JSON blob pre-embedded in system prompt, no tool
  F_prose_push— prose embedded in system prompt, no tool
  F_dbt_meta  — causal parents attached to each metric in the catalog, no tool

F_ontology is reused from Phase 6 (concept_ablation_raw.json → M0 full).
F_json_push / F_prose_push / F_dbt_meta are executed fresh (180 new runs).

Reports:
  - Per-format Wilson 95% CI on hit rate (pooled and per-concept)
  - McNemar paired tests vs F_ontology
  - Side-by-side comparison to decide whether ontology format matters
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
from ontoprobe.rootcause.tools import CausalFormat, OntologyMode

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
        "VIP Customer",
        build_vip_focused_scenarios,
        "m_101",
        "Revenue",
        "VIP Customer",
    ),
    ConceptTest(
        "Discount Campaign",
        build_discount_focused_scenarios,
        "m_101",
        "Revenue",
        "Discount Campaign",
    ),
    ConceptTest(
        "Seasonal Product",
        build_seasonal_focused_scenarios,
        "m_107",
        "Seasonal Revenue",
        "Seasonal Product",
    ),
]


FORMATS: list[tuple[str, CausalFormat | None, str]] = [
    ("F_ontology", CausalFormat.ONTOLOGY, "pull via list_parent_causes (existing M0)"),
    ("F_json_push", CausalFormat.JSON_PUSH, "flat JSON embedded in system prompt"),
    ("F_prose_push", CausalFormat.PROSE_PUSH, "prose embedded in system prompt"),
    ("F_dbt_meta", CausalFormat.DBT_META, "parents attached to metric catalog"),
]


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


def _to_trace_stats(data: dict) -> TraceStats:
    return TraceStats(
        hit=data["hit"],
        reported_concept=data.get("reported_concept", ""),
        iterations=data.get("iterations", 0),
        tool_calls=data.get("iterations", 0),
        compare_calls=data.get("compare_calls", 0),
        list_parent_calls=data.get("list_parent_calls", 0),
        queried_metrics=data.get("queried_metrics", []),
        on_gt_path_queries=0,
        on_any_ancestor_queries=0,
        wrong_branch_queries=data.get("wrong_branch_queries", 0),
        precision_gt_path=data.get("precision_gt_path"),
        precision_any_ancestor=data.get("precision_any_ancestor"),
        stopped_reason="loaded",
        cost_usd=data.get("cost_usd", 0.0),
    )


def _load_phase6() -> dict[str, dict[str, dict[str, dict]]]:
    """concept_ablation_raw.json: {concept_label: {mode_label: {sid: stats}}}."""
    path = RESULTS_DIR / "concept_ablation_raw.json"
    with open(path) as f:
        return json.load(f)


def _load_checkpoint() -> dict[str, dict[str, dict[str, dict]]]:
    path = RESULTS_DIR / "format_ablation_raw.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _checkpoint_save(
    all_results: dict[str, dict[str, dict[str, TraceStats]]],
) -> None:
    path = RESULTS_DIR / "format_ablation_raw.json"
    with open(path, "w") as f:
        json.dump(
            {
                fmt_label: {
                    concept_label: {
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
                        for sid, s in concept_results.items()
                    }
                    for concept_label, concept_results in fmt_results.items()
                }
                for fmt_label, fmt_results in all_results.items()
            },
            f,
            indent=2,
        )


def _run_format_on_concept(
    fmt_label: str,
    causal_format: CausalFormat,
    ct: ConceptTest,
) -> dict[str, TraceStats]:
    scenarios = ct.builder()
    results: dict[str, TraceStats] = {}
    console.print(f"[bold blue]  {fmt_label} / {ct.label}[/]")
    for s in scenarios:
        if causal_format == CausalFormat.ONTOLOGY:
            trace = run_rootcause_agent(
                anomaly_metric_id=ct.anomaly_metric_id,
                round_a=s.baseline.round_id,
                round_b=s.anomaly.round_id,
                ontology_mode=OntologyMode.FULL,
            )
        else:
            trace = run_rootcause_agent(
                anomaly_metric_id=ct.anomaly_metric_id,
                round_a=s.baseline.round_id,
                round_b=s.anomaly.round_id,
                causal_format=causal_format,
            )
        stats = summarize_trace(
            trace, ct.anomaly_concept, ct.ground_truth_concept
        )
        results[s.scenario_id] = stats
        mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
        console.print(
            f"    {s.scenario_id:14} shock→{s.anomaly.shocked_to:<5} "
            f"seed={s.seed:3d}  {mark}"
        )
    return results


def main() -> None:
    console.print(
        Panel(
            "[bold]Format-comparison ablation — 4 formats × 60 scenarios (N=240, 180 new runs)[/]\n"
            "[dim]F_ontology reused from Phase 6; F_json/F_prose/F_dbt_meta executed fresh.[/]",
            expand=False,
        )
    )

    # Persist all scenarios so compare_metric_round sees them
    all_scenarios = []
    for ct in CONCEPTS:
        all_scenarios.extend(ct.builder())
    save_scenarios(all_scenarios)

    phase6 = _load_phase6()
    checkpoint = _load_checkpoint()
    if checkpoint:
        console.print(
            f"[dim]Resuming from checkpoint: "
            f"{sum(len(c) for f in checkpoint.values() for c in f.values())} "
            f"(fmt, concept) pairs cached[/]"
        )

    # all_results[fmt_label][concept_label][sid] = TraceStats
    all_results: dict[str, dict[str, dict[str, TraceStats]]] = {}

    for fmt_label, causal_format, description in FORMATS:
        console.print(
            Panel(f"[bold]{fmt_label}[/] — {description}", border_style="yellow")
        )
        fmt_results: dict[str, dict[str, TraceStats]] = {}

        for ct in CONCEPTS:
            # Reuse F_ontology from Phase 6
            if causal_format == CausalFormat.ONTOLOGY:
                raw = phase6[ct.label]["M0 full"]
                fmt_results[ct.label] = {
                    sid: _to_trace_stats(v) for sid, v in raw.items()
                }
                console.print(
                    f"[dim]  {fmt_label} / {ct.label}: reused Phase 6 "
                    f"({sum(1 for s in fmt_results[ct.label].values() if s.hit)}/"
                    f"{len(raw)} hits)[/]"
                )
                continue

            # Resume from checkpoint if already complete
            cached = checkpoint.get(fmt_label, {}).get(ct.label)
            if cached and len(cached) == 20:
                fmt_results[ct.label] = {
                    sid: _to_trace_stats(v) for sid, v in cached.items()
                }
                console.print(
                    f"[dim]  {fmt_label} / {ct.label}: reused checkpoint "
                    f"({sum(1 for s in fmt_results[ct.label].values() if s.hit)}/"
                    f"{len(cached)} hits)[/]"
                )
                continue

            fmt_results[ct.label] = _run_format_on_concept(
                fmt_label, causal_format, ct
            )
            all_results[fmt_label] = fmt_results
            _checkpoint_save(all_results)

        all_results[fmt_label] = fmt_results
        _checkpoint_save(all_results)

    # ---- Per-concept × format hit rate matrix ----
    console.print()
    per_concept = Table(
        title="\nHit rate by concept × format (N=20 each cell)",
        show_lines=True,
    )
    per_concept.add_column("Concept")
    for fmt_label, _, _ in FORMATS:
        per_concept.add_column(fmt_label, justify="right")

    pooled_by_fmt: dict[str, int] = {f[0]: 0 for f in FORMATS}
    for ct in CONCEPTS:
        row = [ct.label]
        for fmt_label, _, _ in FORMATS:
            r = all_results[fmt_label][ct.label]
            hits = sum(1 for s in r.values() if s.hit)
            pooled_by_fmt[fmt_label] += hits
            row.append(f"{hits}/20 = {hits / 20 * 100:.0f}%")
        per_concept.add_row(*row)

    # Pooled row
    pooled_row = ["[bold]POOLED[/]"]
    for fmt_label, _, _ in FORMATS:
        hits = pooled_by_fmt[fmt_label]
        lo, hi = _wilson_ci(hits, 60)
        pooled_row.append(
            f"{hits}/60 = {hits / 60 * 100:.0f}% [{lo * 100:.0f}%, {hi * 100:.0f}%]"
        )
    per_concept.add_row(*pooled_row, style="bold")
    console.print(per_concept)

    # ---- McNemar vs F_ontology ----
    mcnemar_table = Table(
        title="\nMcNemar paired test — each format vs F_ontology (pooled N=60)",
        show_lines=True,
    )
    mcnemar_table.add_column("Format")
    mcnemar_table.add_column("b (fmt-only)", justify="right")
    mcnemar_table.add_column("c (ontology-only)", justify="right")
    mcnemar_table.add_column("p (two-sided, exact)", justify="right")
    mcnemar_table.add_column("Interp")

    ontology_results = all_results["F_ontology"]
    for fmt_label, causal_format, _ in FORMATS:
        if causal_format == CausalFormat.ONTOLOGY:
            continue
        fmt_results = all_results[fmt_label]
        b = 0
        c = 0
        for ct in CONCEPTS:
            o = ontology_results[ct.label]
            f = fmt_results[ct.label]
            for sid in o:
                if f[sid].hit and not o[sid].hit:
                    b += 1
                elif o[sid].hit and not f[sid].hit:
                    c += 1
        p = _mcnemar_exact(b, c)
        if p < 0.05 and c > b:
            interp = "Ontology > format"
        elif p < 0.05 and b > c:
            interp = "Format > ontology"
        else:
            interp = "Equivalent"
        mcnemar_table.add_row(
            fmt_label, str(b), str(c), f"{p:.4f}", interp
        )
    console.print(mcnemar_table)

    # ---- Headline ----
    console.print()
    headline_lines = []
    for fmt_label, _, _ in FORMATS:
        hits = pooled_by_fmt[fmt_label]
        lo, hi = _wilson_ci(hits, 60)
        headline_lines.append(
            f"  {fmt_label:14} {hits}/60 ({hits / 60 * 100:.0f}%, "
            f"CI [{lo * 100:.0f}%, {hi * 100:.0f}%])"
        )
    console.print(
        Panel(
            "[bold]Pooled hit rates (N=60 per format)[/]\n"
            + "\n".join(headline_lines),
            title="Headline",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
