"""Live LLM demo: show T1 vs T2 side by side for a single hypothesis."""

from __future__ import annotations

import subprocess
import textwrap
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ontoprobe.evaluation.confirmatory import FIXTURES, build_runner_prompt

console = Console(width=120)


def _call_llm(prompt: str, model: str = "opus") -> tuple[str, float]:
    t0 = time.time()
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "text", "--model", model],
        capture_output=True,
        text=True,
        timeout=120,
    )
    dt = time.time() - t0
    if result.returncode != 0:
        return f"[ERROR] {result.stderr.strip()}", dt
    return result.stdout.strip(), dt


def run_llm_demo(hid: str = "H6") -> None:
    hid = hid.upper()
    if hid not in FIXTURES:
        console.print(f"[red]Unknown hypothesis: {hid}. Available: {sorted(FIXTURES.keys())}[/red]")
        return

    fixture = FIXTURES[hid]
    console.print()
    console.print(Panel(
        f"[bold]{hid}[/bold]: {fixture.claim}\n\n"
        f"[dim]Expected magnitude (L3 only): {fixture.l3_expected_magnitude}[/dim]",
        title="LLM Demo — T1 vs T2 比較",
        border_style="cyan",
    ))

    console.print("\n[bold cyan]Query Result:[/bold cyan]")
    console.print(fixture.query_result_table)

    # Run L0
    console.print("\n[bold yellow]Running L0 (期待値なし)...[/bold yellow]")
    prompt_l0 = build_runner_prompt(fixture, 0)
    output_l0, dt_l0 = _call_llm(prompt_l0)
    console.print(f"[dim]({dt_l0:.1f}s)[/dim]")

    # Run L3
    console.print("\n[bold green]Running L3 (期待値あり)...[/bold green]")
    prompt_l3 = build_runner_prompt(fixture, 3)
    output_l3, dt_l3 = _call_llm(prompt_l3)
    console.print(f"[dim]({dt_l3:.1f}s)[/dim]")

    # Parse JSON safely
    import json
    from ontoprobe.hypotheses.llm_backend import extract_json

    def _parse(raw: str) -> dict:
        try:
            return extract_json(raw)
        except Exception:
            return {"analysis": raw, "verdict": "?", "evidence_summary": "?"}

    j_l0 = _parse(output_l0)
    j_l3 = _parse(output_l3)

    # Display side by side
    console.print()
    table = Table(title=f"{hid}: L0 vs L3 比較", show_lines=True, width=120)
    table.add_column("", style="bold", width=12)
    table.add_column("L0 (期待値なし)", width=52, style="yellow")
    table.add_column("L3 (期待値あり)", width=52, style="green")

    table.add_row(
        "Verdict",
        j_l0.get("verdict", "?"),
        j_l3.get("verdict", "?"),
    )
    table.add_row(
        "Evidence",
        textwrap.fill(j_l0.get("evidence_summary", "?"), 50),
        textwrap.fill(j_l3.get("evidence_summary", "?"), 50),
    )

    analysis_l0 = j_l0.get("analysis", "")
    analysis_l3 = j_l3.get("analysis", "")
    table.add_row(
        "Analysis",
        textwrap.fill(analysis_l0[:500], 50) + ("..." if len(analysis_l0) > 500 else ""),
        textwrap.fill(analysis_l3[:500], 50) + ("..." if len(analysis_l3) > 500 else ""),
    )

    console.print(table)

    # Highlight the key difference
    console.print()
    def _has_quantitative_expectation(text: str) -> bool:
        """Check if the text compares observed to a specific expected value.

        Mentioning "target" in the context of "target is unknown" does NOT count.
        We look for patterns like "expected 30-50%", "target of 3M", "below the target".
        """
        t = text.lower()
        negations = ["unknown", "not provided", "not given", "not specified", "cannot determine", "impossible"]
        if any(n in t for n in negations):
            has_neg = True
        else:
            has_neg = False
        comparison_phrases = [
            "below the target", "above the target", "exceeds the expected",
            "below the expected", "falls short", "compared to the expected",
            "expected magnitude", "expected 3", "expected range",
            "contradicting the expected", "the expected 3",
        ]
        has_comparison = any(p in t for p in comparison_phrases)
        import re
        has_quant_pattern = bool(re.search(r"expected.*\d+[%xX]|target.*\d[\d,]*", t))
        return has_comparison or (has_quant_pattern and not has_neg)

    has_expectation_l0 = _has_quantitative_expectation(analysis_l0)
    has_expectation_l3 = _has_quantitative_expectation(analysis_l3)

    console.print(Panel(
        f"[yellow]L0 uses expectation language: {'YES' if has_expectation_l0 else 'NO'}[/yellow]\n"
        f"[green]L3 uses expectation language: {'YES' if has_expectation_l3 else 'NO'}[/green]\n\n"
        f"{'[bold]→ T1→T2 frame transition observed![/bold]' if has_expectation_l3 and not has_expectation_l0 else ''}"
        f"{'[dim]→ Both use expectation language (boundary case)[/dim]' if has_expectation_l0 and has_expectation_l3 else ''}"
        f"{'[red]→ Neither uses expectation language (unexpected)[/red]' if not has_expectation_l0 and not has_expectation_l3 else ''}",
        title="T1/T2 判定",
        border_style="magenta",
    ))
