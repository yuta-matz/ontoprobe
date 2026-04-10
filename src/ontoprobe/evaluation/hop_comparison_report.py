"""Generate markdown report for format x hop-count comparison experiment."""

from __future__ import annotations

from pathlib import Path

from ontoprobe.config import ROOT_DIR
from ontoprobe.evaluation.hop_comparison import (
    CellKey,
    Format,
    HopLevel,
    HopLevelSummary,
)

REPORT_PATH = ROOT_DIR / "reports" / "hop_comparison_report.md"

FORMAT_LABELS = {
    Format.RDF: "RDF",
    Format.NL: "NL",
    Format.MEMO: "MEMO",
    Format.DOC: "DOC",
}


def generate_hop_comparison_report(
    summaries: dict[CellKey, HopLevelSummary],
    ground_truths: dict[HopLevel, dict[str, str]],
) -> Path:
    lines: list[str] = []
    hops = list(HopLevel)
    fmts = list(Format)

    first = next(iter(summaries.values()))

    lines.append("# 知識記述形式 x 因果チェーン段数の交差比較レポート")
    lines.append("")
    lines.append("## 概要")
    lines.append("")
    lines.append("知識記述形式（RDF/NL/MEMO/DOC）と因果チェーンの段数（1〜5段）の")
    lines.append("両方を変化させた場合に、LLMの仮説検証精度がどう変動するかを検証した。")
    lines.append("")
    lines.append(f"- **試行回数:** 各セル {first.num_trials} 回")
    lines.append(f"- **組み合わせ:** {len(fmts)} 形式 x {len(hops)} 段数 = {len(fmts)*len(hops)} セル")
    lines.append("")

    # Ground truth
    for hop in hops:
        lines.append(f"### {hop.value} Ground Truth ({len(ground_truths[hop])}件)")
        lines.append("")
        lines.append("| 仮説 | 正解 |")
        lines.append("|------|------|")
        for rule, verdict in ground_truths[hop].items():
            lines.append(f"| {rule} | {verdict} |")
        lines.append("")

    # === Main matrix: accuracy ===
    lines.append("## 1. verdict正答率マトリクス")
    lines.append("")
    header = "| 形式 | " + " | ".join(h.value for h in hops) + " | 平均 |"
    sep = "|------" + "|---" * len(hops) + "|------|"
    lines.append(header)
    lines.append(sep)

    for fmt in fmts:
        accs = [summaries[(fmt, hop)].accuracy for hop in hops]
        avg = sum(accs) / len(accs)
        row = f"| **{FORMAT_LABELS[fmt]}** |"
        for a in accs:
            row += f" {a:.1%} |"
        row += f" **{avg:.1%}** |"
        lines.append(row)

    # Column averages
    col_avg_row = "| **平均** |"
    for hop in hops:
        avg = sum(summaries[(fmt, hop)].accuracy for fmt in fmts) / len(fmts)
        col_avg_row += f" **{avg:.1%}** |"
    grand_avg = sum(summaries[k].accuracy for k in summaries) / len(summaries)
    col_avg_row += f" {grand_avg:.1%} |"
    lines.append(col_avg_row)
    lines.append("")

    # === Coverage matrix ===
    lines.append("## 2. 仮説カバレッジマトリクス")
    lines.append("")
    header = "| 形式 | " + " | ".join(h.value for h in hops) + " |"
    sep = "|------" + "|---" * len(hops) + "|"
    lines.append(header)
    lines.append(sep)

    for fmt in fmts:
        row = f"| **{FORMAT_LABELS[fmt]}** |"
        for hop in hops:
            row += f" {summaries[(fmt, hop)].coverage:.1%} |"
        lines.append(row)
    lines.append("")

    # === Consistency matrix ===
    lines.append("## 3. 一貫性マトリクス")
    lines.append("")
    header = "| 形式 | " + " | ".join(h.value for h in hops) + " |"
    sep = "|------" + "|---" * len(hops) + "|"
    lines.append(header)
    lines.append(sep)

    for fmt in fmts:
        row = f"| **{FORMAT_LABELS[fmt]}** |"
        for hop in hops:
            s = summaries[(fmt, hop)]
            avg_cons = sum(s.consistency.values()) / max(1, len(s.consistency))
            row += f" {avg_cons:.1%} |"
        lines.append(row)
    lines.append("")

    # === Trial count ===
    lines.append("## 4. 有効試行数マトリクス")
    lines.append("")
    header = "| 形式 | " + " | ".join(h.value for h in hops) + " |"
    sep = "|------" + "|---" * len(hops) + "|"
    lines.append(header)
    lines.append(sep)
    for fmt in fmts:
        row = f"| **{FORMAT_LABELS[fmt]}** |"
        for hop in hops:
            row += f" {len(summaries[(fmt, hop)].trials)} |"
        lines.append(row)
    lines.append("")

    # === Raw trial data ===
    lines.append("## 5. 全試行データ")
    lines.append("")
    lines.append("| 形式 | 段数 | Trial | 仮説 | LLM | 正解 | 一致 |")
    lines.append("|------|------|-------|------|-----|------|------|")
    for fmt in fmts:
        for hop in hops:
            for t in sorted(
                summaries[(fmt, hop)].trials,
                key=lambda x: (x.trial_id, x.rule_name),
            ):
                mark = "OK" if t.is_correct else "NG"
                lines.append(
                    f"| {fmt.value.upper()} | {hop.value} | {t.trial_id} "
                    f"| {t.rule_name[:35]} | {t.llm_verdict} "
                    f"| {t.expected_verdict} | {mark} |"
                )
    lines.append("")

    # === Analysis ===
    lines.append("## 6. 考察")
    lines.append("")

    # Format effect (row averages)
    lines.append("### 形式別平均正答率（段数の影響を平均化）")
    lines.append("")
    for fmt in fmts:
        avg = sum(summaries[(fmt, hop)].accuracy for hop in hops) / len(hops)
        bar = "#" * int(avg * 40)
        lines.append(f"- **{FORMAT_LABELS[fmt]}**: {bar} {avg:.1%}")
    lines.append("")

    # Hop effect (column averages)
    lines.append("### 段数別平均正答率（形式の影響を平均化）")
    lines.append("")
    for hop in hops:
        avg = sum(summaries[(fmt, hop)].accuracy for fmt in fmts) / len(fmts)
        bar = "#" * int(avg * 40)
        lines.append(f"- **{hop.value}**: {bar} {avg:.1%}")
    lines.append("")

    # Interaction effects
    lines.append("### 交互作用")
    lines.append("")

    # Check if hop degradation is worse for some formats
    degradations: dict[Format, float] = {}
    for fmt in fmts:
        acc_1 = summaries[(fmt, HopLevel.HOP_1)].accuracy
        acc_3 = summaries[(fmt, HopLevel.HOP_3)].accuracy
        degradations[fmt] = acc_1 - acc_3

    max_deg_fmt = max(degradations, key=degradations.get)  # type: ignore
    min_deg_fmt = min(degradations, key=degradations.get)  # type: ignore

    lines.append("1-hop → 3-hop の精度変化（形式別）:")
    lines.append("")
    for fmt in fmts:
        d = degradations[fmt]
        direction = "劣化" if d > 0 else ("改善" if d < 0 else "変化なし")
        lines.append(f"- **{FORMAT_LABELS[fmt]}**: {d:+.1%} ({direction})")
    lines.append("")

    if max(degradations.values()) - min(degradations.values()) > 0.1:
        lines.append(
            f"形式によって段数の影響が異なる。"
            f"**{FORMAT_LABELS[max_deg_fmt]}** が最も段数増加の影響を受けやすく、"
            f"**{FORMAT_LABELS[min_deg_fmt]}** が最も耐性がある。"
        )
    else:
        lines.append("段数の影響は形式によらずほぼ均一であった。")
    lines.append("")

    # Summary
    lines.append("### 総括")
    lines.append("")

    # Identify the dominant factor
    format_spread = max(
        sum(summaries[(fmt, hop)].accuracy for hop in hops) / len(hops) for fmt in fmts
    ) - min(
        sum(summaries[(fmt, hop)].accuracy for hop in hops) / len(hops) for fmt in fmts
    )
    hop_spread = max(
        sum(summaries[(fmt, hop)].accuracy for fmt in fmts) / len(fmts) for hop in hops
    ) - min(
        sum(summaries[(fmt, hop)].accuracy for fmt in fmts) / len(fmts) for hop in hops
    )

    lines.append(f"- 形式による精度差: {format_spread:.1%}")
    lines.append(f"- 段数による精度差: {hop_spread:.1%}")
    lines.append("")

    if format_spread > hop_spread:
        lines.append(
            "**知識記述形式が段数よりも大きな影響要因**である。"
            "多段階推論の精度向上には、チェーンの分解よりも"
            "知識の記述方式の最適化が優先されるべき。"
        )
    elif hop_spread > format_spread:
        lines.append(
            "**段数が形式よりも大きな影響要因**である。"
            "因果チェーンが長くなるほど精度が低下する傾向があり、"
            "グラフDBやTool Useによるチェーン分解が有効な対策になりうる。"
        )
    else:
        lines.append(
            "形式と段数の影響はほぼ同程度であった。"
            "両方の最適化を並行して進めることが推奨される。"
        )
    lines.append("")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text)
    print(f"Report generated: {REPORT_PATH}")
    return REPORT_PATH
