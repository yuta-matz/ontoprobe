"""Live LLM demo: show T1 vs T2 side by side for a single hypothesis."""

from __future__ import annotations

import re
import subprocess
import textwrap
import time

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ontoprobe.evaluation.confirmatory import FIXTURES, build_runner_prompt
from ontoprobe.hypotheses.llm_backend import extract_json

console = Console(width=120)

JAPANESE_WRAPPER = "必ず日本語で回答してください。分析・verdict・evidence_summary すべて日本語で書いてください。\n\n"

CLAIM_JA = {
    "H1": "Q4の売上はQ1-Q3の平均より高い",
    "H2": "割引キャンペーン日の注文数は非キャンペーン日より多い",
    "H3": "VIP顧客の平均注文額はNew顧客より高い",
    "H4": "季節商品のQ4売上はQ1-Q3平均より高い",
    "H5": "割引キャンペーン日の平均注文額は非キャンペーン日より低い",
    "H6": "東京の Q4 売上は社内目標を達成している",
    "H7": "VIP顧客は新規顧客より1人あたりの注文回数が多い",
    "H8": "Q4 において12月の売上は10月の売上を上回る",
}


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


def _parse(raw: str) -> dict:
    try:
        return extract_json(raw)
    except Exception:
        return {"analysis": raw, "verdict": "?", "evidence_summary": "?"}


VERDICT_JA = {
    "supported": "支持",
    "contradicted": "否定",
    "inconclusive": "判定不能",
}


def _has_quantitative_expectation(text: str) -> bool:
    t = text.lower()
    # If verdict is inconclusive and text mentions target/goal is unknown,
    # this is T1 (acknowledging absence), not T2 (comparing to known target)
    negations = [
        "unknown", "not provided", "cannot determine", "impossible",
        "知らない", "不明", "判定できない", "判断できません", "わからない",
        "提供されていない", "目標が示されていない", "不可能",
        "具体的な数値が", "基準値が欠如", "ターゲット値が不",
    ]
    hypotheticals = [
        "であれば", "だとすれば", "if the target", "if it were",
        "仮に目標が", "目標が.*であれば",
    ]
    is_negation = any(n in t for n in negations)
    is_hypothetical = any(re.search(h, t) for h in hypotheticals)
    definitive_comparison = [
        "目標を下回", "目標を上回", "目標の下限", "目標レンジ",
        "想定を超", "期待を下回", "想定の.*倍", "想定と.*乖離",
        "期待値.*%", "目標未達", "期待以下", "想定以上", "想定未満",
        "below the target", "above the target", "exceeds the expected",
        "below the expected", "falls short of the target",
    ]
    has_definitive = any(re.search(p, t) for p in definitive_comparison)
    if has_definitive:
        return True
    if is_negation or is_hypothetical:
        return False
    # Fallback: check for quantitative pattern with explicit numbers
    if re.search(r"(expected|想定|期待).{0,20}\d+[%xX倍]", t):
        return True
    return False


def run_llm_demo(hid: str = "H6") -> None:
    hid = hid.upper()
    if hid not in FIXTURES:
        console.print(f"[red]Unknown hypothesis: {hid}. Available: {sorted(FIXTURES.keys())}[/red]")
        return

    fixture = FIXTURES[hid]
    claim_ja = CLAIM_JA.get(hid, fixture.claim)

    console.print()
    console.print(Panel(
        f"[bold]{hid}[/bold]: {claim_ja}\n\n"
        f"[dim]期待値(L3のみ): {fixture.l3_expected_magnitude}[/dim]",
        title="LLM デモ — 期待値なし vs あり",
        border_style="cyan",
    ))

    console.print("\n[bold cyan]クエリ結果:[/bold cyan]")
    console.print(fixture.query_result_table)

    # Run L0
    console.print("\n[bold yellow]L0 実行中（期待値なし）...[/bold yellow]")
    prompt_l0 = JAPANESE_WRAPPER + build_runner_prompt(fixture, 0)
    output_l0, dt_l0 = _call_llm(prompt_l0)
    console.print(f"[dim]({dt_l0:.1f}秒)[/dim]")

    # Run L3
    console.print("\n[bold green]L3 実行中（期待値あり）...[/bold green]")
    prompt_l3 = JAPANESE_WRAPPER + build_runner_prompt(fixture, 3)
    output_l3, dt_l3 = _call_llm(prompt_l3)
    console.print(f"[dim]({dt_l3:.1f}秒)[/dim]")

    j_l0 = _parse(output_l0)
    j_l3 = _parse(output_l3)

    verdict_l0 = j_l0.get("verdict", "?")
    verdict_l3 = j_l3.get("verdict", "?")
    verdict_l0_ja = VERDICT_JA.get(verdict_l0, verdict_l0)
    verdict_l3_ja = VERDICT_JA.get(verdict_l3, verdict_l3)

    # Display side by side
    console.print()
    table = Table(title=f"{hid}: 期待値なし vs あり", show_lines=True, width=120)
    table.add_column("", style="bold", width=12)
    table.add_column("L0（期待値なし）", width=52, style="yellow")
    table.add_column("L3（期待値あり）", width=52, style="green")

    table.add_row("判定", verdict_l0_ja, verdict_l3_ja)
    table.add_row(
        "根拠",
        textwrap.fill(j_l0.get("evidence_summary", "?"), 50),
        textwrap.fill(j_l3.get("evidence_summary", "?"), 50),
    )

    analysis_l0 = j_l0.get("analysis", "")
    analysis_l3 = j_l3.get("analysis", "")
    table.add_row(
        "分析",
        textwrap.fill(analysis_l0[:600], 50) + ("..." if len(analysis_l0) > 600 else ""),
        textwrap.fill(analysis_l3[:600], 50) + ("..." if len(analysis_l3) > 600 else ""),
    )

    console.print(table)

    # T1/T2 detection
    has_exp_l0 = _has_quantitative_expectation(analysis_l0)
    has_exp_l3 = _has_quantitative_expectation(analysis_l3)

    console.print()
    if has_exp_l3 and not has_exp_l0:
        msg = (
            "[yellow]L0: 期待値との比較なし（T1: 記述モード）[/yellow]\n"
            "[green]L3: 期待値との比較あり（T2: 判定モード）[/green]\n\n"
            "[bold magenta]→ T1 → T2 のフレーム遷移を確認！[/bold magenta]\n"
            "[dim]期待値プロパティが LLM の認知モードを切り替えた[/dim]"
        )
    elif has_exp_l0 and has_exp_l3:
        msg = (
            "[yellow]L0: 期待値言語あり（boundary case）[/yellow]\n"
            "[green]L3: 期待値言語あり[/green]\n\n"
            "[dim]→ L0 でも部分的に期待値比較が出現（教科書的仮説の boundary condition）[/dim]"
        )
    else:
        msg = (
            "[yellow]L0: 期待値との比較なし[/yellow]\n"
            f"[green]L3: 期待値との比較{'あり' if has_exp_l3 else 'なし'}[/green]"
        )

    console.print(Panel(msg, title="T1/T2 フレーム遷移の判定", border_style="magenta"))
