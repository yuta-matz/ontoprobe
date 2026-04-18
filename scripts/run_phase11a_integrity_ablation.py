"""Phase 11a: ontology integrity check — what if the ontology is wrong?

Phase 10 showed that a correctly-inverted ontology overrides the wrong
LLM prior and lifts hit rate from 27% → 78%. But that assumed the
ontology was accurate. In real deployments the ontology author might
be wrong: a rule copied from a textbook that doesn't actually apply to
this organization, or a stale rule that no longer matches current
business reality.

This experiment tests the critical "what if wrong?" case:

  cell I-W : Inverted DGP + Normal ontology (pointing the wrong way)

and compares against Phase 10:

  cell I-  : Inverted DGP + no ontology    (LLM relies on prior)
  cell II  : Inverted DGP + inverted ontology (reality-matching)

The key question: is a wrong ontology WORSE than no ontology?

Possible outcomes:
  I-W << I- : Wrong ontology actively misleads. Integrity critical.
  I-W ≈ I-  : LLM ignores wrong ontology, falls back on prior.
  I-W ≈ II  : LLM is so ontology-reliant it gets confused either way.
  I-W >> I- : Wrong ontology is still better than nothing (unlikely).

Runs 60 new scenarios (3 concepts × 20) and reuses Phase 10 cells
I- and II from phase10_inversion_raw.json.
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
CHECKPOINT_PATH = RESULTS_DIR / "phase11a_integrity_raw.json"


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


def _load_phase10() -> dict:
    path = RESULTS_DIR / "phase10_inversion_raw.json"
    with open(path) as f:
        return json.load(f)


def _load_checkpoint() -> dict:
    if not CHECKPOINT_PATH.exists():
        return {}
    with open(CHECKPOINT_PATH) as f:
        return json.load(f)


def _save_checkpoint(results: dict[str, dict[str, TraceStats]]) -> None:
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(
            {
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
                for concept_label, concept_results in results.items()
            },
            f,
            indent=2,
        )


def main() -> None:
    console.print(
        Panel(
            "[bold]Phase 11a — Ontology integrity check[/]\n"
            "[dim]Run Inverted DGP × Normal ontology (I-W). "
            "Compare against Phase 10 I- (no ontology) and II (correct ontology).[/]",
            expand=False,
        )
    )

    all_scenarios: list[Scenario] = []
    for c in INVERTED_CONCEPTS:
        all_scenarios.extend(c.builder())
    save_scenarios(all_scenarios)

    checkpoint = _load_checkpoint()
    phase10 = _load_phase10()

    # Run fresh: I-W (inverted DGP + normal ontology, variant=None)
    console.print(
        Panel(
            "[bold]I-W: Inverted DGP + Normal ontology[/] "
            "(ontology points the WRONG direction vs reality)",
            border_style="red",
        )
    )
    iw_results: dict[str, dict[str, TraceStats]] = {}
    for concept in INVERTED_CONCEPTS:
        cached = checkpoint.get(concept.label)
        if cached and len(cached) == 20:
            iw_results[concept.label] = {
                sid: _to_trace_stats(v) for sid, v in cached.items()
            }
            hits = sum(1 for s in iw_results[concept.label].values() if s.hit)
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
                ontology_mode=OntologyMode.FULL,
                ontology_variant=None,  # default = normal ontology
            )
            stats = summarize_trace(
                trace, concept.anomaly_concept, concept.ground_truth_concept
            )
            concept_results[s.scenario_id] = stats
            mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
            console.print(
                f"    {s.scenario_id:20} shock→{s.anomaly.shocked_to:<5} "
                f"seed={s.seed:3d}  {mark}"
            )
        iw_results[concept.label] = concept_results
        _save_checkpoint(iw_results)

    # Load Phase 10 cells for comparison
    def _from_phase10(cell_label: str) -> dict[str, dict[str, TraceStats]]:
        return {
            concept_label: {
                sid: _to_trace_stats(v)
                for sid, v in phase10[cell_label][concept_label].items()
            }
            for concept_label in phase10[cell_label]
        }

    phase10_i_ = _from_phase10("I- no ontology")
    phase10_ii = _from_phase10("II inverted ontology")

    # ---- 3-cell aggregate table ----
    console.print()
    agg = Table(
        title="\nPhase 11a: Inverted DGP, 3 ontology conditions (N=60 pooled)",
        show_lines=True,
    )
    agg.add_column("Cell")
    agg.add_column("Ontology")
    agg.add_column("Hit (95% CI)", justify="right")

    def _tally(cell: dict[str, dict[str, TraceStats]]) -> tuple[int, int]:
        total = 0
        hits = 0
        for concept_results in cell.values():
            total += len(concept_results)
            hits += sum(1 for s in concept_results.values() if s.hit)
        return hits, total

    hits_i, n_i = _tally(phase10_i_)
    hits_iw, n_iw = _tally(iw_results)
    hits_ii, n_ii = _tally(phase10_ii)

    for label, ontology_desc, hits, n in [
        ("I-", "No ontology (LLM uses its wrong prior)", hits_i, n_i),
        (
            "I-W",
            "Normal ontology (WRONG for this world)",
            hits_iw,
            n_iw,
        ),
        ("II", "Inverted ontology (correct for this world)", hits_ii, n_ii),
    ]:
        lo, hi = _wilson_ci(hits, n)
        agg.add_row(
            label,
            ontology_desc,
            f"{hits}/{n} = {hits / n * 100:.0f}% [{lo * 100:.0f}%, {hi * 100:.0f}%]",
        )
    console.print(agg)

    # ---- Pairwise McNemar ----
    console.print()
    pair = Table(title="\nPairwise McNemar tests", show_lines=True)
    pair.add_column("Pair")
    pair.add_column("b", justify="right")
    pair.add_column("c", justify="right")
    pair.add_column("p (exact, 2-sided)", justify="right")
    pair.add_column("Interp")

    def _paired(
        a_cell: dict[str, dict[str, TraceStats]],
        b_cell: dict[str, dict[str, TraceStats]],
    ) -> tuple[int, int]:
        b_hit = 0
        c_hit = 0
        for concept_label in a_cell:
            a_results = a_cell[concept_label]
            b_results = b_cell[concept_label]
            for sid in a_results:
                if b_results[sid].hit and not a_results[sid].hit:
                    b_hit += 1
                elif a_results[sid].hit and not b_results[sid].hit:
                    c_hit += 1
        return b_hit, c_hit

    # I-W vs I-
    b, c = _paired(phase10_i_, iw_results)
    p = _mcnemar_exact(b, c)
    if p < 0.05 and b > c:
        interp = "Wrong ontology > No ontology"
    elif p < 0.05 and c > b:
        interp = "Wrong ontology < No ontology (HURTS)"
    else:
        interp = "No significant difference"
    pair.add_row("I-W vs I-", str(b), str(c), f"{p:.4f}", interp)

    # I-W vs II
    b, c = _paired(iw_results, phase10_ii)
    p = _mcnemar_exact(b, c)
    if p < 0.05 and b > c:
        interp = "Correct > Wrong ontology"
    elif p < 0.05 and c > b:
        interp = "Wrong > Correct ontology"
    else:
        interp = "No significant difference"
    pair.add_row("I-W vs II", str(b), str(c), f"{p:.4f}", interp)

    console.print(pair)

    # ---- Per-concept breakdown ----
    console.print()
    per = Table(title="\nPer-concept breakdown", show_lines=True)
    per.add_column("Concept")
    per.add_column("I-", justify="right")
    per.add_column("I-W", justify="right")
    per.add_column("II", justify="right")
    per.add_column("I-W vs I- Δ", justify="right")

    for concept in INVERTED_CONCEPTS:
        i_res = phase10_i_[concept.label]
        iw_res = iw_results[concept.label]
        ii_res = phase10_ii[concept.label]
        i_hits = sum(1 for s in i_res.values() if s.hit)
        iw_hits = sum(1 for s in iw_res.values() if s.hit)
        ii_hits = sum(1 for s in ii_res.values() if s.hit)
        per.add_row(
            concept.label,
            f"{i_hits}/20 = {i_hits / 20 * 100:.0f}%",
            f"{iw_hits}/20 = {iw_hits / 20 * 100:.0f}%",
            f"{ii_hits}/20 = {ii_hits / 20 * 100:.0f}%",
            f"{(iw_hits - i_hits) / 20 * 100:+.0f}",
        )
    console.print(per)


if __name__ == "__main__":
    main()
