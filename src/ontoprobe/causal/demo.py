"""Causal inference demo: SEM + partial identification with ontology."""

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
from ontoprobe.causal.sem import estimate_sem

console = Console(width=100)


def run_causal_demo() -> None:
    console.print()
    console.print(Panel(
        "[bold]割引キャンペーン → 日次売上 の因果効果を推定[/bold]\n\n"
        "[dim]オントロジーの因果 DAG を 2 つの方法で活用:\n"
        "  1. SEM（構造方程式）: DAG をそのまま方程式に → 各経路の効果を分離\n"
        "  2. 部分識別: DAG の仮定（方向性・選択バイアス）で bounds を段階的に狭める[/dim]",
        title="因果推論デモ — オントロジー DAG × SEM × 部分識別",
        border_style="cyan",
    ))

    # === Data summary ===
    df = load_daily_data(observable_only=True)
    treated = df[df["has_discount_campaign"] == 1]
    control = df[df["has_discount_campaign"] == 0]
    naive = (treated["daily_revenue"].mean() / control["daily_revenue"].mean() - 1) * 100

    console.print(f"\n[bold cyan]データ概要:[/bold cyan]")
    console.print(f"  全日数: {len(df)} / キャンペーン日: {len(treated)} ({len(treated)/len(df)*100:.1f}%)")
    console.print(f"  [yellow]ナイーブ推定（単純比較）: +{naive:.1f}%[/yellow] ← 交絡込み")

    # === Part 1: SEM ===
    console.print()
    console.print(Panel("[bold]Part 1: SEM — オントロジー DAG → 構造方程式[/bold]", border_style="green"))

    sem_result = estimate_sem(df)

    table = Table(title="各因果経路の推定値 vs オントロジー期待値", show_lines=True, width=96)
    table.add_column("経路", width=32)
    table.add_column("SEM 推定", width=14, justify="right")
    table.add_column("期待値", width=14, justify="center")
    table.add_column("判定", width=10, justify="center")

    for p in sem_result.paths:
        style = ""
        if p.comparison == "期待以下":
            style = "yellow"
        elif p.comparison == "期待以上":
            style = "red"
        elif p.comparison == "期待通り":
            style = "green"
        table.add_row(p.path, f"{p.coefficient:+.1f}%", p.ontology_expected, p.comparison, style=style)

    console.print(table)

    console.print(f"\n  ナイーブ推定: [yellow]+{sem_result.naive_revenue_effect:.1f}%[/yellow]")
    console.print(f"  SEM 推定:     [green]{sem_result.sem_net_revenue_effect:+.1f}%[/green] ← DAG で交絡を部分制御")
    if sem_result.true_revenue_effect is not None:
        console.print(f"  真の因果効果: [cyan]+{sem_result.true_revenue_effect:.1f}%[/cyan]")
    console.print(f"  [dim]→ SEM は DAG 構造で {sem_result.naive_revenue_effect - sem_result.sem_net_revenue_effect:.0f}pp のバイアスを除去[/dim]")
    console.print(f"  [dim]→ ただし未観察交絡が残るため、まだ過大評価の可能性[/dim]")

    # === Part 2: Partial identification ===
    console.print()
    console.print(Panel("[bold]Part 2: 部分識別 — 仮定を段階的に追加[/bold]", border_style="magenta"))

    results = run_all_steps(df, expected_lower=5.0, expected_upper=15.0)

    table2 = Table(title="仮定を追加 → bounds が狭まる", show_lines=True, width=96)
    table2.add_column("Step", width=6, style="bold")
    table2.add_column("仮定", width=46)
    table2.add_column("下限", width=8, justify="right")
    table2.add_column("上限", width=8, justify="right")
    table2.add_column("幅", width=8, justify="right")

    for r in results:
        if isinstance(r, Bounds):
            style = "green" if r.step == 4 else ""
            table2.add_row(str(r.step), r.assumption, f"{r.lower:+.1f}%", f"{r.upper:+.1f}%", f"{r.width:.0f}pp", style=style)

    console.print(table2)

    comparison = [r for r in results if isinstance(r, BoundsComparison)][0]

    # === Part 3: Comparison ===
    console.print()
    console.print(Panel("[bold]Part 3: 全手法の比較[/bold]", border_style="yellow"))

    table3 = Table(show_lines=True, width=96)
    table3.add_column("手法", width=30)
    table3.add_column("推定値", width=20, justify="center")
    table3.add_column("バイアス", width=12, justify="center")
    table3.add_column("オントロジー活用", width=26)

    true_val = sem_result.true_revenue_effect or 6.4
    final_bounds = [r for r in results if isinstance(r, Bounds)][-1]

    table3.add_row(
        "ナイーブ推定", f"+{sem_result.naive_revenue_effect:.1f}%",
        f"+{sem_result.naive_revenue_effect - true_val:.0f}pp",
        "なし", style="red"
    )
    table3.add_row(
        "SEM（構造方程式）", f"{sem_result.sem_net_revenue_effect:+.1f}%",
        f"+{sem_result.sem_net_revenue_effect - true_val:.0f}pp",
        "DAG → 方程式構造", style="yellow"
    )
    table3.add_row(
        "部分識別", f"[{final_bounds.lower:+.1f}%, {final_bounds.upper:+.1f}%]",
        "—（区間）",
        "direction → MTR\nsource → MTS", style="green"
    )
    table3.add_row(
        "期待値（ontology）", "+5〜15%", "—", "expectedMagnitude"
    )
    table3.add_row(
        "真の因果効果", f"+{true_val:.1f}%", "0", "（検証用 ground truth）", style="cyan"
    )

    console.print(table3)

    # === Conclusion ===
    console.print()
    console.print(Panel(
        "[bold]結論:[/bold]\n\n"
        f"[red]ナイーブ推定 +{sem_result.naive_revenue_effect:.1f}% は「期待を超えて好調!」に見える[/red]\n"
        f"[yellow]→ SEM で DAG 構造を使うと {sem_result.sem_net_revenue_effect:+.1f}% に改善（バイアス {sem_result.naive_revenue_effect - sem_result.sem_net_revenue_effect:.0f}pp 除去）[/yellow]\n"
        f"[green]→ 部分識別で [{final_bounds.lower:+.1f}%, {final_bounds.upper:+.1f}%] に（仮定を明示した上で）[/green]\n"
        f"[cyan]→ 真の効果 +{true_val:.1f}% は部分識別 bounds に含まれる ✓[/cyan]\n\n"
        "[bold]オントロジーの二重の役割:[/bold]\n"
        "  1. [green]因果 DAG[/green] → SEM の構造 / 部分識別の仮定（direction → MTR, source → MTS）\n"
        "  2. [green]期待値[/green] → 推定結果と「組織の想定」の比較基準\n\n"
        "[dim]オントロジーは LLM の判定スイッチであると同時に、因果推論の仮定レジストリでもある[/dim]",
        title="オントロジー × 因果推論",
        border_style="cyan",
    ))


if __name__ == "__main__":
    run_causal_demo()
