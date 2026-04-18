"""Phase 11b: cross-model validity on Claude Haiku 4.5.

Phase 10 showed a +52pp effect of ontology-override on Claude Sonnet.
But is that Sonnet-specific? The骨子 v2 Slide 21 limits explicitly
mention 'Claude モデルのみ' as a weakness. This experiment replicates
the Phase 10 inverted DGP cells on Haiku 4.5 — a smaller, cheaper
Claude model — to test whether the effect generalizes across model
capacity within the Claude family.

Cells re-run on Haiku:
  I-H : Inverted DGP + no ontology (same as I- but on Haiku)
  II-H: Inverted DGP + inverted ontology (same as II but on Haiku)

Pairs with Phase 10 Sonnet cells for comparison:
  Sonnet I- = 16/60 = 27%
  Sonnet II = 47/60 = 78%
  Δ +52pp

Predicted outcomes:
  - Haiku shows similar gradient but smaller magnitude (smaller model
    follows instructions less reliably)
  - Haiku baseline (I-H) might be lower or similar (smaller models also
    have less strong priors? or more random?)
  - Haiku with ontology (II-H) might fail to follow the inverted rules
    consistently, showing less improvement

A Sonnet-only replication of Phase 10 effect on Haiku would mean the
finding is model-size-independent within Claude; a failure would mean
it's a Sonnet-specific behavior worth investigating further.

120 new runs total (2 cells × 60 scenarios), ~30 min, ~$4 on Haiku.
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
    build_inverted_discount_scenarios,
    build_inverted_seasonal_scenarios,
    build_inverted_vip_scenarios,
    save_scenarios,
)
from ontoprobe.rootcause.eval import TraceStats, summarize_trace
from ontoprobe.rootcause.tools import OntologyMode

console = Console(width=130)
RESULTS_DIR = DATA_DIR / "rootcause"
CHECKPOINT_PATH = RESULTS_DIR / "phase11b_haiku_raw.json"
HAIKU_MODEL = "haiku"


@dataclass
class InvertedConcept:
    label: str
    builder: Callable[[], list[Scenario]]
    anomaly_metric_id: str
    anomaly_concept: str
    ground_truth_concept: str


INVERTED_CONCEPTS: list[InvertedConcept] = [
    InvertedConcept(
        "VIP Customer (inverted)",
        build_inverted_vip_scenarios,
        "m_101",
        "Revenue",
        "VIP Customer",
    ),
    InvertedConcept(
        "Discount Campaign (inverted)",
        build_inverted_discount_scenarios,
        "m_101",
        "Revenue",
        "Discount Campaign",
    ),
    InvertedConcept(
        "Seasonal Product (inverted)",
        build_inverted_seasonal_scenarios,
        "m_107",
        "Seasonal Revenue",
        "Seasonal Product",
    ),
]


CELLS: list[tuple[str, OntologyMode, str | None, str]] = [
    (
        "I-H no ontology (Haiku)",
        OntologyMode.NONE,
        None,
        "Haiku + inverted DGP, no ontology",
    ),
    (
        "II-H inverted ontology (Haiku)",
        OntologyMode.FULL,
        "inverted",
        "Haiku + inverted DGP, inverted ontology",
    ),
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


def _to_trace_stats(d: dict) -> TraceStats:
    return TraceStats(
        hit=d["hit"],
        reported_concept=d.get("reported_concept", ""),
        iterations=d.get("iterations", 0),
        tool_calls=d.get("iterations", 0),
        compare_calls=d.get("compare_calls", 0),
        list_parent_calls=d.get("list_parent_calls", 0),
        queried_metrics=d.get("queried_metrics", []),
        on_gt_path_queries=0,
        on_any_ancestor_queries=0,
        wrong_branch_queries=d.get("wrong_branch_queries", 0),
        precision_gt_path=d.get("precision_gt_path"),
        precision_any_ancestor=d.get("precision_any_ancestor"),
        stopped_reason="loaded",
        cost_usd=d.get("cost_usd", 0.0),
    )


def _load_checkpoint() -> dict:
    if not CHECKPOINT_PATH.exists():
        return {}
    with open(CHECKPOINT_PATH) as f:
        return json.load(f)


def _save_checkpoint(
    results: dict[str, dict[str, dict[str, TraceStats]]],
) -> None:
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(
            {
                cell_label: {
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
                    for concept_label, concept_results in cell_results.items()
                }
                for cell_label, cell_results in results.items()
            },
            f,
            indent=2,
        )


def _load_phase10_sonnet() -> dict:
    path = RESULTS_DIR / "phase10_inversion_raw.json"
    with open(path) as f:
        return json.load(f)


def main() -> None:
    console.print(
        Panel(
            "[bold]Phase 11b — Haiku 4.5 replication[/]\n"
            "[dim]Replicate Phase 10 I- and II cells on Haiku to test model robustness.[/]",
            expand=False,
        )
    )

    all_scenarios: list[Scenario] = []
    for c in INVERTED_CONCEPTS:
        all_scenarios.extend(c.builder())
    save_scenarios(all_scenarios)

    checkpoint = _load_checkpoint()
    all_results: dict[str, dict[str, dict[str, TraceStats]]] = {}

    for cell_label, mode, variant, description in CELLS:
        console.print(
            Panel(f"[bold]{cell_label}[/] — {description}", border_style="yellow")
        )
        cell_results: dict[str, dict[str, TraceStats]] = {}
        for concept in INVERTED_CONCEPTS:
            cached = checkpoint.get(cell_label, {}).get(concept.label)
            if cached and len(cached) == 20:
                cell_results[concept.label] = {
                    sid: _to_trace_stats(v) for sid, v in cached.items()
                }
                hits = sum(1 for s in cell_results[concept.label].values() if s.hit)
                console.print(
                    f"[dim]  {concept.label}: reused checkpoint ({hits}/20 hits)[/]"
                )
                continue

            console.print(f"[bold blue]  {concept.label}[/]")
            scenarios = concept.builder()
            concept_results: dict[str, TraceStats] = {}
            for s in scenarios:
                trace = run_rootcause_agent(
                    anomaly_metric_id=concept.anomaly_metric_id,
                    round_a=s.baseline.round_id,
                    round_b=s.anomaly.round_id,
                    ontology_mode=mode,
                    ontology_variant=variant,
                    model=HAIKU_MODEL,
                )
                stats = summarize_trace(
                    trace,
                    concept.anomaly_concept,
                    concept.ground_truth_concept,
                )
                concept_results[s.scenario_id] = stats
                mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
                console.print(
                    f"    {s.scenario_id:20} shock→{s.anomaly.shocked_to:<5} "
                    f"seed={s.seed:3d}  {mark}"
                )
            cell_results[concept.label] = concept_results
            all_results[cell_label] = cell_results
            _save_checkpoint(all_results)

        all_results[cell_label] = cell_results
        _save_checkpoint(all_results)

    # Load Phase 10 Sonnet for comparison
    phase10 = _load_phase10_sonnet()

    def _tally(cell: dict[str, dict[str, TraceStats]]) -> tuple[int, int]:
        total = 0
        hits = 0
        for cr in cell.values():
            total += len(cr)
            hits += sum(1 for s in cr.values() if s.hit)
        return hits, total

    def _tally_raw(cell: dict) -> tuple[int, int]:
        total = 0
        hits = 0
        for cr in cell.values():
            total += len(cr)
            hits += sum(1 for s in cr.values() if s["hit"])
        return hits, total

    # ---- Side-by-side comparison ----
    console.print()
    comp = Table(
        title="\nSonnet (Phase 10) vs Haiku (Phase 11b) on inverted DGP",
        show_lines=True,
    )
    comp.add_column("Cell")
    comp.add_column("Sonnet hit (Phase 10)", justify="right")
    comp.add_column("Haiku hit (Phase 11b)", justify="right")
    comp.add_column("Δ (Haiku − Sonnet) pp", justify="right")

    sonnet_i = _tally_raw(phase10["I- no ontology"])
    sonnet_ii = _tally_raw(phase10["II inverted ontology"])
    haiku_i = _tally(all_results["I-H no ontology (Haiku)"])
    haiku_ii = _tally(all_results["II-H inverted ontology (Haiku)"])

    comp.add_row(
        "I- no ontology",
        f"{sonnet_i[0]}/{sonnet_i[1]} = {sonnet_i[0] / sonnet_i[1] * 100:.0f}%",
        f"{haiku_i[0]}/{haiku_i[1]} = {haiku_i[0] / haiku_i[1] * 100:.0f}%",
        f"{(haiku_i[0] / haiku_i[1] - sonnet_i[0] / sonnet_i[1]) * 100:+.0f}",
    )
    comp.add_row(
        "II inverted ontology",
        f"{sonnet_ii[0]}/{sonnet_ii[1]} = {sonnet_ii[0] / sonnet_ii[1] * 100:.0f}%",
        f"{haiku_ii[0]}/{haiku_ii[1]} = {haiku_ii[0] / haiku_ii[1] * 100:.0f}%",
        f"{(haiku_ii[0] / haiku_ii[1] - sonnet_ii[0] / sonnet_ii[1]) * 100:+.0f}",
    )
    console.print(comp)

    # ---- Within-model effect sizes ----
    console.print()
    effect = Table(
        title="\nWithin-model ontology effect (Inverted DGP)", show_lines=True
    )
    effect.add_column("Model")
    effect.add_column("No ontology", justify="right")
    effect.add_column("With ontology", justify="right")
    effect.add_column("Δ pp", justify="right")

    sonnet_delta = (sonnet_ii[0] - sonnet_i[0]) / sonnet_i[1] * 100
    haiku_delta = (haiku_ii[0] - haiku_i[0]) / haiku_i[1] * 100

    effect.add_row(
        "Sonnet 4.6 (Phase 10)",
        f"{sonnet_i[0] / sonnet_i[1] * 100:.0f}%",
        f"{sonnet_ii[0] / sonnet_ii[1] * 100:.0f}%",
        f"{sonnet_delta:+.0f}",
    )
    effect.add_row(
        "Haiku 4.5 (Phase 11b)",
        f"{haiku_i[0] / haiku_i[1] * 100:.0f}%",
        f"{haiku_ii[0] / haiku_ii[1] * 100:.0f}%",
        f"{haiku_delta:+.0f}",
    )
    console.print(effect)

    # ---- Per-concept breakdown on Haiku ----
    console.print()
    per = Table(
        title="\nHaiku per-concept breakdown (inverted DGP)", show_lines=True
    )
    per.add_column("Concept")
    per.add_column("I-H no ontology", justify="right")
    per.add_column("II-H inverted ontology", justify="right")
    per.add_column("Δ pp", justify="right")
    for concept in INVERTED_CONCEPTS:
        i_res = all_results["I-H no ontology (Haiku)"][concept.label]
        ii_res = all_results["II-H inverted ontology (Haiku)"][concept.label]
        i_hits = sum(1 for s in i_res.values() if s.hit)
        ii_hits = sum(1 for s in ii_res.values() if s.hit)
        per.add_row(
            concept.label,
            f"{i_hits}/20 = {i_hits / 20 * 100:.0f}%",
            f"{ii_hits}/20 = {ii_hits / 20 * 100:.0f}%",
            f"{(ii_hits - i_hits) / 20 * 100:+.0f}",
        )
    console.print(per)


if __name__ == "__main__":
    main()
