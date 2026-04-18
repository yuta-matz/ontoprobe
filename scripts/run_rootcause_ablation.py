"""Multi-scenario A/B ablation for the root-cause loop.

Runs the same scenarios under two conditions:
  A — with ontology: agent has list_parent_causes + compare_metric_round
  B — without ontology: agent has only compare_metric_round

Both conditions see identical opaque metric ids with identical neutral
descriptions, so the no-ontology baseline cannot infer causal structure
from friendly metric names.

For each scenario we log the full agent trace, then compute:
  - hit (reported root cause concept matches ground truth)
  - iterations, compare calls, list_parent calls
  - branch precision against the ontology DAG:
      precision_gt_path = fraction of queried metrics lying on the
        (ground_truth → anomaly) path in the causal DAG
      precision_any_ancestor = fraction lying anywhere in the ancestors
        of the anomaly concept
  - cost
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ontoprobe.rootcause.agent import AgentTrace, run_rootcause_agent
from ontoprobe.rootcause.data_gen import build_scenarios, save_scenarios
from ontoprobe.rootcause.eval import TraceStats, summarize_trace
from ontoprobe.rootcause.tools import OntologyMode

console = Console(width=120)


@dataclass
class AnomalyPrime:
    """How the orchestrator introduces the anomaly to the agent."""

    scenario_id: str
    anomaly_metric_id: str
    anomaly_concept: str  # for eval only — not shown to agent


ANOMALY_PRIMES: list[AnomalyPrime] = [
    AnomalyPrime("S1", "m_103", "Order Volume"),
    AnomalyPrime("S2", "m_101", "Revenue"),
    AnomalyPrime("S3", "m_107", "Seasonal Revenue"),
]


def _print_trace(label: str, trace: AgentTrace) -> None:
    console.print(f"\n[bold]{label}[/] ({len(trace.tool_calls)} tool calls)")
    for i, tc in enumerate(trace.tool_calls, 1):
        args = json.dumps(tc["input"], ensure_ascii=False)
        if tc["tool"] == "compare_metric_round":
            r = tc["result"]
            dp = r.get("delta_pct") if isinstance(r, dict) else None
            dp_str = f"Δ {dp:+.1f}%" if dp is not None else ""
            console.print(f"  [{i:2}] [cyan]{tc['tool']}[/]({args}) {dp_str}")
        elif tc["tool"] == "list_parent_causes":
            r = tc["result"]
            causes = (
                ", ".join(
                    f"{p['cause_concept']}({p.get('metric_id','—')})"
                    for p in r.get("parent_causes", [])
                )
                if isinstance(r, dict)
                else ""
            )
            console.print(f"  [{i:2}] [magenta]{tc['tool']}[/]({args}) → {causes}")
        else:
            console.print(f"  [{i:2}] [green]{tc['tool']}[/]({args})")


def _fmt_precision(p: float | None) -> str:
    return "—" if p is None else f"{p * 100:.0f}%"


def main() -> None:
    console.print(
        Panel(
            "[bold]Rootcause multi-scenario ablation: A (with ontology) vs B (no ontology)[/]\n"
            "[dim]Opaque metric ids, neutral descriptions in both conditions.[/]",
            expand=False,
        )
    )

    scenarios = build_scenarios()
    save_scenarios(scenarios)
    scenario_map = {s.scenario_id: s for s in scenarios}

    all_results: list[dict] = []

    for prime in ANOMALY_PRIMES:
        scenario = scenario_map[prime.scenario_id]
        gt_concept = scenario.anomaly.shocked_concept

        console.print()
        console.print(
            Panel(
                f"[bold]{prime.scenario_id}:[/] {scenario.description}\n"
                f"Anomaly metric: {prime.anomaly_metric_id} "
                f"(concept: {prime.anomaly_concept})\n"
                f"Ground-truth shocked concept: {gt_concept} "
                f"({scenario.anomaly.shocked_lever}: "
                f"{scenario.anomaly.shocked_from} → {scenario.anomaly.shocked_to})",
                title=f"Scenario {prime.scenario_id}",
                border_style="yellow",
            )
        )

        console.print("[bold blue]Running A (with ontology)...[/]")
        trace_a = run_rootcause_agent(
            anomaly_metric_id=prime.anomaly_metric_id,
            round_a=scenario.baseline.round_id,
            round_b=scenario.anomaly.round_id,
            ontology_mode=OntologyMode.FULL,
        )
        console.print("[bold blue]Running B (no ontology)...[/]")
        trace_b = run_rootcause_agent(
            anomaly_metric_id=prime.anomaly_metric_id,
            round_a=scenario.baseline.round_id,
            round_b=scenario.anomaly.round_id,
            ontology_mode=OntologyMode.NONE,
        )

        stats_a = summarize_trace(trace_a, prime.anomaly_concept, gt_concept)
        stats_b = summarize_trace(trace_b, prime.anomaly_concept, gt_concept)

        _print_trace("A (with ontology)", trace_a)
        _print_trace("B (no ontology)", trace_b)

        all_results.append(
            {
                "scenario": prime.scenario_id,
                "gt_concept": gt_concept,
                "anomaly_concept": prime.anomaly_concept,
                "A": stats_a,
                "B": stats_b,
            }
        )

    # ---- Per-scenario result table ----
    console.print()
    table = Table(title="\nPer-scenario results", show_lines=True)
    table.add_column("Scenario")
    table.add_column("Ground truth")
    table.add_column("Cond")
    table.add_column("Hit", justify="center")
    table.add_column("Steps", justify="right")
    table.add_column("Cmp", justify="right")
    table.add_column("LP", justify="right")
    table.add_column("Prec(GT)", justify="right")
    table.add_column("Prec(Anc)", justify="right")
    table.add_column("Wrong", justify="right")
    table.add_column("$", justify="right")

    for row in all_results:
        for cond_name, s in [("A", row["A"]), ("B", row["B"])]:
            hit = "[green]✓[/]" if s.hit else "[red]✗[/]"
            table.add_row(
                row["scenario"] if cond_name == "A" else "",
                row["gt_concept"] if cond_name == "A" else "",
                cond_name,
                hit,
                str(s.iterations),
                str(s.compare_calls),
                str(s.list_parent_calls),
                _fmt_precision(s.precision_gt_path),
                _fmt_precision(s.precision_any_ancestor),
                str(s.wrong_branch_queries),
                f"${s.cost_usd:.3f}",
            )
    console.print(table)

    # ---- Aggregate summary ----
    def _agg(cond: str) -> dict[str, float]:
        stats = [r[cond] for r in all_results]
        n = len(stats)
        return {
            "hit_rate": sum(1 for s in stats if s.hit) / n,
            "avg_steps": sum(s.iterations for s in stats) / n,
            "avg_compare": sum(s.compare_calls for s in stats) / n,
            "avg_list_parent": sum(s.list_parent_calls for s in stats) / n,
            "avg_prec_gt": sum(
                s.precision_gt_path for s in stats if s.precision_gt_path is not None
            )
            / max(1, sum(1 for s in stats if s.precision_gt_path is not None)),
            "avg_prec_anc": sum(
                s.precision_any_ancestor
                for s in stats
                if s.precision_any_ancestor is not None
            )
            / max(
                1, sum(1 for s in stats if s.precision_any_ancestor is not None)
            ),
            "avg_wrong": sum(s.wrong_branch_queries for s in stats) / n,
            "total_cost": sum(s.cost_usd for s in stats),
        }

    agg_a = _agg("A")
    agg_b = _agg("B")

    summary = Table(title="\nAggregate (3 scenarios)", show_lines=True)
    summary.add_column("Metric")
    summary.add_column("A: with ontology", justify="right")
    summary.add_column("B: no ontology", justify="right")
    for key, label, fmt in [
        ("hit_rate", "Hit rate", lambda v: f"{v * 100:.0f}%"),
        ("avg_steps", "Avg iterations", lambda v: f"{v:.1f}"),
        ("avg_compare", "Avg compare calls", lambda v: f"{v:.1f}"),
        ("avg_list_parent", "Avg list_parent calls", lambda v: f"{v:.1f}"),
        ("avg_prec_gt", "Avg precision (GT path)", lambda v: f"{v * 100:.0f}%"),
        ("avg_prec_anc", "Avg precision (any ancestor)", lambda v: f"{v * 100:.0f}%"),
        ("avg_wrong", "Avg wrong-branch queries", lambda v: f"{v:.1f}"),
        ("total_cost", "Total cost (USD)", lambda v: f"${v:.3f}"),
    ]:
        summary.add_row(label, fmt(agg_a[key]), fmt(agg_b[key]))
    console.print(summary)


if __name__ == "__main__":
    main()
