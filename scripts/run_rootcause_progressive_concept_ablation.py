"""Progressive property ablation across 3 concepts.

Extends Phase 7 from VIP alone to all three class-typed concepts
(VIP / Discount / Seasonal). For each concept we build the same 5-tier
ladder (T0 → T4) and compare the marginal lift of each added property.

T0 and T4 are loaded from ``data/rootcause/concept_ablation_raw.json``
(Phase 6 output) for all three concepts. T1/T2/T3 are run fresh on
Discount and Seasonal (120 new runs). For VIP we reload T1/T2/T3 from
``data/rootcause/progressive_vip_ablation_raw.json`` (Phase 7 output)
so no work is duplicated.

Outputs:
  - Per-concept 5-tier ladder
  - Cross-concept marginal lift matrix (which property adds most for
    which concept)
  - Pooled ladder across all 3 concepts
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
class Tier:
    label: str
    mode: OntologyMode
    added: str


TIERS: list[Tier] = [
    Tier("T0 none", OntologyMode.NONE, "—"),
    Tier("T1 concepts", OntologyMode.CONCEPTS_ONLY, "+ parent concept labels"),
    Tier("T2 +metric_id", OntologyMode.STRUCT_AND_METRIC_ID, "+ :measuredBy"),
    Tier("T3 +rule labels", OntologyMode.NO_DESC_MAG, "+ rdfs:label on rules"),
    Tier("T4 full", OntologyMode.FULL, "+ :hasDescription + magnitude"),
]

NEW_TIERS = {"T1 concepts", "T2 +metric_id", "T3 +rule labels"}


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


def _load_concept_ablation() -> dict[str, dict[str, dict[str, dict]]]:
    """concept_ablation_raw.json: {concept_label: {mode_label: {sid: stats_dict}}}."""
    path = RESULTS_DIR / "concept_ablation_raw.json"
    with open(path) as f:
        return json.load(f)


def _load_progressive_vip() -> dict[str, dict[str, dict]]:
    """progressive_vip_ablation_raw.json: {tier_label: {sid: stats_dict}}."""
    path = RESULTS_DIR / "progressive_vip_ablation_raw.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _load_checkpoint() -> dict[str, dict[str, dict[str, dict]]]:
    """Resume from an earlier partial run if the raw file exists."""
    path = RESULTS_DIR / "progressive_concept_ablation_raw.json"
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _checkpoint_save(
    all_results: dict[str, dict[str, dict[str, "TraceStats"]]],
) -> None:
    path = RESULTS_DIR / "progressive_concept_ablation_raw.json"
    with open(path, "w") as f:
        json.dump(
            {
                concept_label: {
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
                    for tier_label, tier_results in concept_results.items()
                }
                for concept_label, concept_results in all_results.items()
            },
            f,
            indent=2,
        )


def _run_tier(
    ct: ConceptTest, tier: Tier, scenarios: list[Scenario]
) -> dict[str, TraceStats]:
    console.print(
        f"[bold blue]  {ct.label} / {tier.label}[/] ({tier.added})"
    )
    results: dict[str, TraceStats] = {}
    for s in scenarios:
        trace = run_rootcause_agent(
            anomaly_metric_id=ct.anomaly_metric_id,
            round_a=s.baseline.round_id,
            round_b=s.anomaly.round_id,
            ontology_mode=tier.mode,
        )
        stats = summarize_trace(trace, ct.anomaly_concept, ct.ground_truth_concept)
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
            "[bold]Progressive ablation × 3 concepts[/]\n"
            "[dim]Load T0/T4 from Phase 6; reload VIP T1/T2/T3 from Phase 7; "
            "run Discount and Seasonal T1/T2/T3 fresh (120 new runs).[/]",
            expand=False,
        )
    )

    concept_phase6 = _load_concept_ablation()
    progressive_vip = _load_progressive_vip()
    checkpoint = _load_checkpoint()
    if checkpoint:
        console.print(
            f"[dim]Resuming from checkpoint: "
            f"{sum(len(v) for v in checkpoint.values())} concept/tier pairs cached[/]"
        )

    # Ensure scenarios are persisted to rounds.csv so compare_metric_round can run
    all_scenarios = []
    for ct in CONCEPTS:
        all_scenarios.extend(ct.builder())
    save_scenarios(all_scenarios)

    # concept_label → tier_label → {sid: TraceStats}
    all_results: dict[str, dict[str, dict[str, TraceStats]]] = {}

    for ct in CONCEPTS:
        concept_results: dict[str, dict[str, TraceStats]] = {}
        scenarios = ct.builder()

        for tier in TIERS:
            if tier.label == "T0 none":
                raw = concept_phase6[ct.label]["M4 none"]
                concept_results[tier.label] = {
                    sid: _to_trace_stats(v) for sid, v in raw.items()
                }
                console.print(
                    f"[dim]{ct.label} / {tier.label}: reused Phase 6 "
                    f"({sum(1 for s in concept_results[tier.label].values() if s.hit)}/{len(raw)} hits)[/]"
                )
                continue
            if tier.label == "T4 full":
                raw = concept_phase6[ct.label]["M0 full"]
                concept_results[tier.label] = {
                    sid: _to_trace_stats(v) for sid, v in raw.items()
                }
                console.print(
                    f"[dim]{ct.label} / {tier.label}: reused Phase 6 "
                    f"({sum(1 for s in concept_results[tier.label].values() if s.hit)}/{len(raw)} hits)[/]"
                )
                continue
            if ct.label == "VIP Customer" and tier.label in progressive_vip:
                raw = progressive_vip[tier.label]
                concept_results[tier.label] = {
                    sid: _to_trace_stats(v) for sid, v in raw.items()
                }
                console.print(
                    f"[dim]{ct.label} / {tier.label}: reused Phase 7 "
                    f"({sum(1 for s in concept_results[tier.label].values() if s.hit)}/{len(raw)} hits)[/]"
                )
                continue

            # Resume from checkpoint if available
            cached = checkpoint.get(ct.label, {}).get(tier.label)
            if cached and len(cached) == len(scenarios):
                concept_results[tier.label] = {
                    sid: _to_trace_stats(v) for sid, v in cached.items()
                }
                console.print(
                    f"[dim]{ct.label} / {tier.label}: reused checkpoint "
                    f"({sum(1 for s in concept_results[tier.label].values() if s.hit)}/{len(cached)} hits)[/]"
                )
                continue

            # Run fresh, then checkpoint after each tier
            concept_results[tier.label] = _run_tier(ct, tier, scenarios)
            all_results[ct.label] = concept_results
            _checkpoint_save(all_results)

        all_results[ct.label] = concept_results
        _checkpoint_save(all_results)

    # Persist
    out_path = RESULTS_DIR / "progressive_concept_ablation_raw.json"
    with open(out_path, "w") as f:
        json.dump(
            {
                concept_label: {
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
                    for tier_label, tier_results in concept_results.items()
                }
                for concept_label, concept_results in all_results.items()
            },
            f,
            indent=2,
        )
    console.print(f"\n[dim]Raw results → {out_path}[/]")

    # ---- Per-concept tier ladders ----
    for ct in CONCEPTS:
        console.print()
        ladder = Table(
            title=f"\n{ct.label} — tier ladder (N=20)", show_lines=True
        )
        ladder.add_column("Tier")
        ladder.add_column("Added property")
        ladder.add_column("Hit (95% CI)", justify="right")
        ladder.add_column("Δpp", justify="right")
        ladder.add_column("McNemar p", justify="right")

        concept_results = all_results[ct.label]
        prev_label = None
        prev_hits = None
        for tier in TIERS:
            r = concept_results[tier.label]
            n = len(r)
            hits = sum(1 for s in r.values() if s.hit)
            lo, hi = _wilson_ci(hits, n)
            ci = f"{hits}/{n} = {hits / n * 100:.0f}% [{lo * 100:.0f}%, {hi * 100:.0f}%]"

            delta = "—"
            p_str = "—"
            if prev_hits is not None and prev_label is not None:
                delta = f"{(hits - prev_hits) / n * 100:+.0f}"
                prev_r = concept_results[prev_label]
                b = sum(
                    1 for sid in r if r[sid].hit and not prev_r[sid].hit
                )
                c = sum(
                    1 for sid in r if (not r[sid].hit) and prev_r[sid].hit
                )
                p = _mcnemar_exact(b, c)
                p_str = f"{p:.3f}"
                if p < 0.05:
                    p_str = f"[bold green]{p_str}[/]"
            ladder.add_row(tier.label, tier.added, ci, delta, p_str)
            prev_hits = hits
            prev_label = tier.label
        console.print(ladder)

    # ---- Cross-concept marginal lift matrix ----
    console.print()
    lift = Table(
        title="\nMarginal lift per added property (Δpp vs previous tier)",
        show_lines=True,
    )
    lift.add_column("Transition")
    for ct in CONCEPTS:
        lift.add_column(ct.label, justify="right")
    lift.add_column("POOLED (60)", justify="right")

    for i, tier in enumerate(TIERS):
        if i == 0:
            continue
        prev_tier = TIERS[i - 1]
        row = [f"{prev_tier.label} → {tier.label}"]
        pooled_prev = 0
        pooled_curr = 0
        for ct in CONCEPTS:
            r = all_results[ct.label][tier.label]
            prev_r = all_results[ct.label][prev_tier.label]
            curr_hits = sum(1 for s in r.values() if s.hit)
            prev_hits = sum(1 for s in prev_r.values() if s.hit)
            delta = (curr_hits - prev_hits) / 20 * 100
            row.append(f"{delta:+.0f}")
            pooled_curr += curr_hits
            pooled_prev += prev_hits
        pooled_delta = (pooled_curr - pooled_prev) / 60 * 100
        row.append(f"[bold]{pooled_delta:+.0f}[/]")
        lift.add_row(*row)
    console.print(lift)

    # ---- Pooled ladder ----
    console.print()
    pooled_ladder = Table(
        title="\nPooled tier ladder (N=60 across 3 concepts)", show_lines=True
    )
    pooled_ladder.add_column("Tier")
    pooled_ladder.add_column("Added property")
    pooled_ladder.add_column("Hit (95% CI)", justify="right")
    pooled_ladder.add_column("Δpp", justify="right")
    pooled_ladder.add_column("McNemar p", justify="right")

    prev_pooled_hits = None
    prev_pooled_tier = None
    for tier in TIERS:
        total_hits = 0
        total_n = 0
        for ct in CONCEPTS:
            r = all_results[ct.label][tier.label]
            total_hits += sum(1 for s in r.values() if s.hit)
            total_n += len(r)
        lo, hi = _wilson_ci(total_hits, total_n)
        ci = f"{total_hits}/{total_n} = {total_hits / total_n * 100:.0f}% [{lo * 100:.0f}%, {hi * 100:.0f}%]"

        delta = "—"
        p_str = "—"
        if prev_pooled_hits is not None and prev_pooled_tier is not None:
            delta = f"{(total_hits - prev_pooled_hits) / total_n * 100:+.0f}"
            # Pooled McNemar across all 3 concepts
            b = 0
            c = 0
            for ct in CONCEPTS:
                r = all_results[ct.label][tier.label]
                prev_r = all_results[ct.label][prev_pooled_tier]
                b += sum(1 for sid in r if r[sid].hit and not prev_r[sid].hit)
                c += sum(
                    1 for sid in r if (not r[sid].hit) and prev_r[sid].hit
                )
            p = _mcnemar_exact(b, c)
            p_str = f"{p:.4f}"
            if p < 0.05:
                p_str = f"[bold green]{p_str}[/]"
        pooled_ladder.add_row(tier.label, tier.added, ci, delta, p_str)
        prev_pooled_hits = total_hits
        prev_pooled_tier = tier.label
    console.print(pooled_ladder)


if __name__ == "__main__":
    main()
