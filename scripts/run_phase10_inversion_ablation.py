"""Phase 10 2×2 ablation: does ontology override wrong LLM prior?

Design:

                 | No ontology      | With ontology           |
  Normal DGP     | N- (Phase 6 reuse) | NN (Phase 6 reuse)    |
  Inverted DGP   | I- (NEW 60 runs)   | II (NEW 60 runs)      |

The critical test is the Inverted-DGP row. Both cells start from an
LLM prior that points the WRONG direction (e.g. 'VIPs should have
higher AOV, so Revenue goes down when VIPs churn' — but in the inverted
DGP, Revenue actually goes UP when VIPs churn because VIPs have lower
AOV in this world). The question:

  - In I- (no ontology), does the LLM follow its wrong prior and miss?
  - In II (inverted ontology telling the truth), does the LLM override
    its prior and solve the case?

McNemar test on I- vs II paired N=60 tells us the effect size of
'ontology overrides wrong prior'. Paired with the Phase 6 baseline
(NN - N- = +38pp on normal DGP), we can state whether ontology is
EQUALLY effective, MORE effective, or LESS effective when the prior
is wrong vs aligned.
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
CHECKPOINT_PATH = RESULTS_DIR / "phase10_inversion_raw.json"


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
        "I- no ontology",
        OntologyMode.NONE,
        None,
        "Inverted DGP, no ontology (LLM relies on wrong prior)",
    ),
    (
        "II inverted ontology",
        OntologyMode.FULL,
        "inverted",
        "Inverted DGP, inverted ontology (reality-matching)",
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


def _load_checkpoint() -> dict[str, dict[str, dict[str, dict]]]:
    if not CHECKPOINT_PATH.exists():
        return {}
    with open(CHECKPOINT_PATH) as f:
        return json.load(f)


def _save_checkpoint(
    all_results: dict[str, dict[str, dict[str, TraceStats]]],
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
                for cell_label, cell_results in all_results.items()
            },
            f,
            indent=2,
        )


def _load_phase6() -> dict[str, dict[str, dict[str, dict]]]:
    path = RESULTS_DIR / "concept_ablation_raw.json"
    with open(path) as f:
        return json.load(f)


def _run_cell_on_concept(
    cell_label: str,
    mode: OntologyMode,
    variant: str | None,
    concept: InvertedConcept,
) -> dict[str, TraceStats]:
    scenarios = concept.builder()
    results: dict[str, TraceStats] = {}
    console.print(f"[bold blue]  {cell_label} / {concept.label}[/]")
    for s in scenarios:
        trace = run_rootcause_agent(
            anomaly_metric_id=concept.anomaly_metric_id,
            round_a=s.baseline.round_id,
            round_b=s.anomaly.round_id,
            ontology_mode=mode,
            ontology_variant=variant,
        )
        stats = summarize_trace(
            trace, concept.anomaly_concept, concept.ground_truth_concept
        )
        results[s.scenario_id] = stats
        mark = "[green]✓[/]" if stats.hit else "[red]✗[/]"
        console.print(
            f"    {s.scenario_id:20} shock→{s.anomaly.shocked_to:<5} "
            f"seed={s.seed:3d}  {mark}"
        )
    return results


def main() -> None:
    console.print(
        Panel(
            "[bold]Phase 10 inversion ablation — 2×2 factorial[/]\n"
            "[dim]Inverted DGP × {no ontology, inverted ontology}. "
            "Normal DGP cells reused from Phase 6.[/]",
            expand=False,
        )
    )

    # Persist inverted scenarios so compare_metric_round can read them
    all_scenarios: list[Scenario] = []
    for concept in INVERTED_CONCEPTS:
        all_scenarios.extend(concept.builder())
    save_scenarios(all_scenarios)
    console.print(f"Generated {len(all_scenarios)} inverted scenarios\n")

    checkpoint = _load_checkpoint()
    phase6 = _load_phase6()

    # Build the results map; cell_label → concept_label → sid → TraceStats
    all_results: dict[str, dict[str, dict[str, TraceStats]]] = {}

    # --- Inverted DGP cells (run fresh) ---
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
                console.print(
                    f"[dim]  {cell_label} / {concept.label}: reused checkpoint "
                    f"({sum(1 for s in cell_results[concept.label].values() if s.hit)}/"
                    f"{len(cached)} hits)[/]"
                )
                continue

            cell_results[concept.label] = _run_cell_on_concept(
                cell_label, mode, variant, concept
            )
            all_results[cell_label] = cell_results
            _save_checkpoint(all_results)

        all_results[cell_label] = cell_results
        _save_checkpoint(all_results)

    # --- Reuse Phase 6 for Normal DGP cells ---
    # concept_ablation_raw.json keys use the non-inverted concept labels
    phase6_label_map = {
        "VIP Customer (inverted)": "VIP Customer",
        "Discount Campaign (inverted)": "Discount Campaign",
        "Seasonal Product (inverted)": "Seasonal Product",
    }
    normal_cells: dict[str, dict[str, dict[str, TraceStats]]] = {
        "N- no ontology": {},
        "NN with ontology": {},
    }
    for inv_label, phase6_label in phase6_label_map.items():
        raw_m4 = phase6[phase6_label]["M4 none"]
        raw_m0 = phase6[phase6_label]["M0 full"]
        normal_cells["N- no ontology"][inv_label] = {
            sid: _to_trace_stats(v) for sid, v in raw_m4.items()
        }
        normal_cells["NN with ontology"][inv_label] = {
            sid: _to_trace_stats(v) for sid, v in raw_m0.items()
        }
    all_results["N- no ontology"] = normal_cells["N- no ontology"]
    all_results["NN with ontology"] = normal_cells["NN with ontology"]

    # ---- 2×2 aggregate table ----
    console.print()
    table = Table(
        title="\nPhase 10 2×2 factorial (pooled across 3 concepts, N=60 per cell)",
        show_lines=True,
    )
    table.add_column("DGP")
    table.add_column("Condition")
    table.add_column("Hit (95% CI)", justify="right")

    cell_order = [
        ("Normal", "N- no ontology", "N- no ontology"),
        ("Normal", "NN with ontology", "NN with ontology"),
        ("Inverted", "I- no ontology", "I- no ontology"),
        ("Inverted", "II inverted ontology", "II inverted ontology"),
    ]
    cell_hits: dict[str, int] = {}
    for dgp, display, key in cell_order:
        total_hits = 0
        total_n = 0
        for concept_label in all_results[key]:
            r = all_results[key][concept_label]
            total_hits += sum(1 for s in r.values() if s.hit)
            total_n += len(r)
        cell_hits[key] = total_hits
        lo, hi = _wilson_ci(total_hits, total_n)
        table.add_row(
            dgp,
            display,
            f"{total_hits}/{total_n} = {total_hits / total_n * 100:.0f}% "
            f"[{lo * 100:.0f}%, {hi * 100:.0f}%]",
        )
    console.print(table)

    # ---- Effect-size comparison ----
    console.print()
    effect_table = Table(
        title="\nOntology effect size by DGP direction", show_lines=True
    )
    effect_table.add_column("DGP")
    effect_table.add_column("No ontology", justify="right")
    effect_table.add_column("With ontology", justify="right")
    effect_table.add_column("Δ pp", justify="right")
    effect_table.add_column("McNemar p", justify="right")
    effect_table.add_column("Interp")

    # Normal DGP: N- vs NN
    normal_b, normal_c = 0, 0
    for concept_label in all_results["N- no ontology"]:
        r_no = all_results["N- no ontology"][concept_label]
        r_with = all_results["NN with ontology"][concept_label]
        for sid in r_no:
            if r_with[sid].hit and not r_no[sid].hit:
                normal_b += 1
            elif r_no[sid].hit and not r_with[sid].hit:
                normal_c += 1
    normal_p = _mcnemar_exact(normal_b, normal_c)
    effect_table.add_row(
        "Normal DGP (prior-aligned)",
        f"{cell_hits['N- no ontology']}/60 "
        f"({cell_hits['N- no ontology'] / 60 * 100:.0f}%)",
        f"{cell_hits['NN with ontology']}/60 "
        f"({cell_hits['NN with ontology'] / 60 * 100:.0f}%)",
        f"{(cell_hits['NN with ontology'] - cell_hits['N- no ontology']) / 60 * 100:+.0f}",
        f"{normal_p:.4f}",
        "Ontology helps" if normal_p < 0.05 else "No effect",
    )

    # Inverted DGP: I- vs II
    inv_b, inv_c = 0, 0
    for concept_label in all_results["I- no ontology"]:
        r_no = all_results["I- no ontology"][concept_label]
        r_with = all_results["II inverted ontology"][concept_label]
        for sid in r_no:
            if r_with[sid].hit and not r_no[sid].hit:
                inv_b += 1
            elif r_no[sid].hit and not r_with[sid].hit:
                inv_c += 1
    inv_p = _mcnemar_exact(inv_b, inv_c)
    effect_table.add_row(
        "Inverted DGP (prior-contradicting)",
        f"{cell_hits['I- no ontology']}/60 "
        f"({cell_hits['I- no ontology'] / 60 * 100:.0f}%)",
        f"{cell_hits['II inverted ontology']}/60 "
        f"({cell_hits['II inverted ontology'] / 60 * 100:.0f}%)",
        f"{(cell_hits['II inverted ontology'] - cell_hits['I- no ontology']) / 60 * 100:+.0f}",
        f"{inv_p:.4f}",
        (
            "Ontology overrides wrong prior"
            if inv_p < 0.05 and inv_b > inv_c
            else "No override"
        ),
    )
    console.print(effect_table)

    # ---- Per-concept breakdown ----
    concept_table = Table(
        title="\nPer-concept breakdown (inverted DGP)", show_lines=True
    )
    concept_table.add_column("Concept")
    concept_table.add_column("I- no ontology", justify="right")
    concept_table.add_column("II inverted ontology", justify="right")
    concept_table.add_column("Δ pp", justify="right")
    for concept in INVERTED_CONCEPTS:
        r_no = all_results["I- no ontology"][concept.label]
        r_with = all_results["II inverted ontology"][concept.label]
        hits_no = sum(1 for s in r_no.values() if s.hit)
        hits_with = sum(1 for s in r_with.values() if s.hit)
        concept_table.add_row(
            concept.label,
            f"{hits_no}/20 = {hits_no / 20 * 100:.0f}%",
            f"{hits_with}/20 = {hits_with / 20 * 100:.0f}%",
            f"{(hits_with - hits_no) / 20 * 100:+.0f}",
        )
    console.print(concept_table)


if __name__ == "__main__":
    main()
