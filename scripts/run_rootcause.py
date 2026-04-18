"""Phase 1 entry point for the Section 5.4 root-cause loop verification.

Generates the two-round scenario, primes the agent with the Revenue
anomaly, runs the tool-use loop, and prints the traversal trace
alongside ground truth so we can see whether Claude reached the
injected root cause.
"""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ontoprobe.rootcause.agent import run_rootcause_agent
from ontoprobe.rootcause.data_gen import build_phase1_scenario, save_rounds
from ontoprobe.rootcause.tools import compare_metric_round

console = Console(width=110)


def main() -> None:
    console.print(
        Panel(
            "[bold]Phase 1: Single-scenario root-cause loop[/]\n"
            "[dim]Baseline vs discount-campaigns-withdrawn, one shocked lever.[/]",
            expand=False,
        )
    )

    console.print("[bold blue]Generating rounds...[/]")
    rows, rounds = build_phase1_scenario()
    save_rounds(rows, rounds)
    for r in rounds:
        shock = (
            f"{r.shocked_lever} {r.shocked_from} → {r.shocked_to}"
            if r.shocked_lever
            else "—"
        )
        console.print(f"  {r.round_id} [cyan]{r.label}[/]: shocked {shock}")

    console.print("\n[bold blue]Anomaly detection (round-over-round delta):[/]")
    deltas_table = Table(show_header=True, header_style="bold")
    deltas_table.add_column("Metric")
    deltas_table.add_column("R1", justify="right")
    deltas_table.add_column("R2", justify="right")
    deltas_table.add_column("Δ%", justify="right")
    for metric in [
        "total_revenue",
        "order_count",
        "total_discount",
        "effective_margin",
        "campaign_day_share",
    ]:
        d = compare_metric_round(metric, "R1", "R2")
        deltas_table.add_row(
            metric,
            f"{d['value_a']:,.2f}",
            f"{d['value_b']:,.2f}",
            f"{d['delta_pct']:+.2f}%" if d["delta_pct"] is not None else "—",
        )
    console.print(deltas_table)

    console.print("\n[bold blue]Running agent loop on Revenue anomaly...[/]")
    trace = run_rootcause_agent("total_revenue", "R1", "R2")

    console.print(
        f"\n[bold]Agent trace:[/] {trace.iterations} iterations, "
        f"{len(trace.tool_calls)} tool calls"
    )
    for i, tc in enumerate(trace.tool_calls, 1):
        args = json.dumps(tc["input"], ensure_ascii=False)
        if tc["tool"] == "compare_metric_round":
            r = tc["result"]
            summary = (
                f"Δ {r['delta_pct']:+.1f}%"
                if isinstance(r, dict) and r.get("delta_pct") is not None
                else ""
            )
            console.print(f"  [{i:2}] [cyan]{tc['tool']}[/]({args})  {summary}")
        elif tc["tool"] == "list_parent_causes":
            r = tc["result"]
            if isinstance(r, dict) and "parent_causes" in r:
                causes = ", ".join(p["cause_concept"] for p in r["parent_causes"])
            else:
                causes = ""
            console.print(f"  [{i:2}] [magenta]{tc['tool']}[/]({args})  → {causes}")
        else:
            console.print(f"  [{i:2}] [green]{tc['tool']}[/]({args})")

    console.print(f"\n[bold]Stopped:[/] {trace.stopped_reason}")

    if trace.final_report:
        r = trace.final_report
        console.print(
            Panel(
                f"[bold]Root cause:[/] {r['root_cause_concept']}\n\n"
                + "[bold]Evidence chain:[/]\n"
                + "\n".join(f"  • {s}" for s in r["evidence_chain"])
                + f"\n\n[bold]Recommendation:[/] {r['recommendation']}",
                title="Agent final report",
                border_style="green",
            )
        )
    else:
        console.print("[red]No final report produced.[/]")

    gt = rounds[1]
    hit = (
        trace.final_report
        and gt.shocked_concept.lower() in trace.final_report["root_cause_concept"].lower()
    )
    console.print(
        Panel(
            f"[bold]Injected shock:[/] {gt.shocked_lever} "
            f"({gt.shocked_from} → {gt.shocked_to})\n"
            f"[bold]Ground-truth concept:[/] {gt.shocked_concept}\n"
            f"[bold]Expected downstream:[/] {', '.join(gt.expected_downstream)}\n"
            f"[bold]Hit:[/] {'[green]YES[/]' if hit else '[red]NO[/]'}",
            title="Ground truth",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    main()
