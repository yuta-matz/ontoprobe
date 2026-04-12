"""Causal inference demo: partial identification with ontology assumptions."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ontoprobe.causal.partial_id import (
    Bounds,
    BoundsComparison,
    load_daily_data,
    run_all_steps,
)

console = Console(width=100)


def run_causal_demo() -> None:
    console.print()
    console.print(Panel(
        "[bold]割引キャンペーン → 日次売上 の因果効果を部分識別で推定[/bold]\n\n"
        "[dim]処置: 割引キャンペーン実施日 / 結果: 日次売上\n"
        "オントロジーの期待値: +5〜15%（source: marketing team ネット効果推定）[/dim]",
        title="因果推論デモ — 部分識別 × オントロジー",
        border_style="cyan",
    ))

    # Load data
    df = load_daily_data(observable_only=True)
    treated = df[df["has_discount_campaign"] == True]  # noqa: E712
    control = df[df["has_discount_campaign"] == False]  # noqa: E712

    console.print(f"\n[bold cyan]データ概要:[/bold cyan]")
    console.print(f"  全日数: {len(df)}")
    console.print(f"  キャンペーン日: {len(treated)} ({len(treated)/len(df)*100:.1f}%)")
    console.print(f"  非キャンペーン日: {len(control)}")

    naive = (treated["daily_revenue"].mean() / control["daily_revenue"].mean() - 1) * 100
    console.print(f"\n  [yellow]ナイーブ推定（単純比較）: +{naive:.1f}%[/yellow]")
    console.print(f"  [dim]→ これは交絡を含む。本当にキャンペーンの効果か?[/dim]")

    # Run partial identification
    results = run_all_steps(df, expected_lower=5.0, expected_upper=15.0)

    # Display progressive bounds
    console.print()
    table = Table(title="仮定を段階的に追加 → bounds が狭まる", show_lines=True, width=98)
    table.add_column("Step", width=6, style="bold")
    table.add_column("仮定", width=48)
    table.add_column("下限", width=8, justify="right")
    table.add_column("上限", width=8, justify="right")
    table.add_column("幅", width=8, justify="right")

    for r in results:
        if isinstance(r, Bounds):
            style = "green" if r.step == 4 else ""
            table.add_row(
                str(r.step),
                r.assumption,
                f"{r.lower:+.1f}%",
                f"{r.upper:+.1f}%",
                f"{r.width:.0f}pp",
                style=style,
            )

    console.print(table)

    # Comparison with expectation
    comparison = [r for r in results if isinstance(r, BoundsComparison)][0]

    console.print()
    bounds_bar = _format_bounds_bar(comparison)
    console.print(Panel(
        bounds_bar,
        title="Step 5: bounds × 期待値の比較",
        border_style="magenta",
    ))

    console.print()
    console.print(Panel(
        f"[bold]{comparison.conclusion}[/bold]\n\n"
        "[dim]ナイーブ推定 +23.6% は「期待を超えて好調」に見えるが、\n"
        "部分識別で交絡を考慮すると bounds は [0%, +14.8%] に収まり、\n"
        "期待通りかどうかは確定できない。\n"
        "→ 追加検証（A/Bテスト等）の実施が推奨される。[/dim]",
        title="結論",
        border_style="cyan",
    ))


def _format_bounds_bar(comp: BoundsComparison) -> str:
    """Format a text-based visualization of bounds vs expectation."""
    lines = []
    lines.append(f"  ナイーブ推定:     +23.6%          ← 交絡込み（信頼できない）")
    lines.append(f"")
    lines.append(f"  bounds (Step 4):  [yellow][{comp.bounds.lower:+.1f}% ————————— {comp.bounds.upper:+.1f}%][/yellow]")
    lines.append(f"  期待値(ontology): [green]        [{comp.expected_lower:+.1f}% ——— {comp.expected_upper:+.1f}%][/green]")
    lines.append(f"")
    lines.append(f"  0%        5%        10%       15%       20%       25%")
    lines.append(f"  |---------|---------|---------|---------|---------|")
    lines.append(f"  [yellow]|=========|=========|=========[/yellow][green]|[/green]         [red]×[/red] ← ナイーブ")
    lines.append(f"            [green]|=========|=========[/green]")
    lines.append(f"  [yellow]▲ bounds                      ▲[/yellow]")
    lines.append(f"            [green]▲ 期待値            ▲[/green]")
    return "\n".join(lines)


if __name__ == "__main__":
    run_causal_demo()
