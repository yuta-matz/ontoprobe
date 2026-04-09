"""Generate markdown report for the RDF vs NL vs DOC comparison experiment."""

from __future__ import annotations

from pathlib import Path

from ontoprobe.config import ROOT_DIR
from ontoprobe.evaluation.comparison import Condition, ConditionSummary

REPORT_PATH = ROOT_DIR / "reports" / "knowledge_format_comparison_report.md"

CONDITION_LABELS = {
    Condition.RDF: "RDF（構造化）",
    Condition.NL: "NL（自然言語）",
    Condition.MEMO: "MEMO（社内文書）",
    Condition.DOC: "DOC（議事録）",
}


def _fmt_acc(v: float) -> str:
    if v != v:  # NaN check
        return "N/A"
    return f"{v:.0%}"


def generate_comparison_report(
    summaries: dict[Condition, ConditionSummary],
    ground_truth: dict[str, str],
) -> Path:
    """Generate a markdown comparison report."""
    lines: list[str] = []
    conditions = [c for c in Condition if c in summaries]
    first = summaries[conditions[0]]

    # Header
    lines.append("# 知識記述形式の仮説検証精度比較レポート")
    lines.append("")
    lines.append("## 概要")
    lines.append("")
    lines.append("オントロジーの因果ルールを異なる形式で記述した場合に、")
    lines.append("LLMによる仮説検証の精度にどの程度差が生じるかを比較検証した。")
    lines.append("")
    lines.append("### 比較条件")
    lines.append("")
    lines.append("| 条件 | 説明 |")
    lines.append("|------|------|")
    lines.append("| **RDF（構造化）** | RDF由来の箇条書き（Cause / Effect / Direction / Magnitude） |")
    lines.append("| **NL（自然言語）** | 同一情報を散文パラグラフで記述 |")
    lines.append("| **MEMO（社内文書）** | ルールごとに独立した社内文書（議事録抜粋・Slack・レポート）で記述 |")
    lines.append("| **DOC（議事録）** | 1つのリアルな議事録に全ルールを埋め込み。ノイズ・会話・脱線を含む |")
    lines.append("")
    lines.append(f"- **試行回数:** 各条件 {first.num_trials} 回")
    lines.append(f"- **評価対象ルール:** {len(ground_truth)} 件")
    lines.append("- **Ground Truth:** デモモードのルールベース検証結果")
    lines.append("")

    # Ground truth
    lines.append("### Ground Truth（正解ラベル）")
    lines.append("")
    lines.append("| ルール | 正解verdict |")
    lines.append("|--------|-----------|")
    for rule, verdict in ground_truth.items():
        lines.append(f"| {rule} | {verdict} |")
    lines.append("")

    # Summary table
    lines.append("## 1. 総合比較")
    lines.append("")
    header = "| 指標 | " + " | ".join(CONDITION_LABELS[c] for c in conditions) + " |"
    sep = "|------" + "|" + "|".join("---" for _ in conditions) + "|"
    lines.append(header)
    lines.append(sep)

    # Accuracy row
    acc_row = "| 総合正答率 |"
    for c in conditions:
        acc_row += f" **{summaries[c].accuracy:.1%}** |"
    lines.append(acc_row)

    # Trial count row
    trial_row = "| 有効試行数 |"
    for c in conditions:
        trial_row += f" {len(summaries[c].trials)} |"
    lines.append(trial_row)

    # Consistency row
    cons_row = "| 平均一貫性 |"
    for c in conditions:
        s = summaries[c]
        avg = sum(s.consistency.values()) / len(s.consistency) if s.consistency else 0
        cons_row += f" {avg:.1%} |"
    lines.append(cons_row)
    lines.append("")

    # Per-rule accuracy
    lines.append("## 2. ルール別正答率")
    lines.append("")
    header = "| ルール | " + " | ".join(CONDITION_LABELS[c] for c in conditions) + " |"
    sep = "|--------" + "|" + "|".join("---" for _ in conditions) + "|"
    lines.append(header)
    lines.append(sep)

    per_rules = {c: summaries[c].per_rule_accuracy for c in conditions}
    all_rules = sorted(set().union(*(pr.keys() for pr in per_rules.values())))

    for rule in all_rules:
        row = f"| {rule} |"
        for c in conditions:
            row += f" {_fmt_acc(per_rules[c].get(rule, float('nan')))} |"
        lines.append(row)
    lines.append("")

    # Consistency per rule
    lines.append("## 3. ルール別一貫性（verdict安定度）")
    lines.append("")
    header = "| ルール | " + " | ".join(CONDITION_LABELS[c] for c in conditions) + " |"
    sep = "|--------" + "|" + "|".join("---" for _ in conditions) + "|"
    lines.append(header)
    lines.append(sep)

    cons_data = {c: summaries[c].consistency for c in conditions}
    all_cons_rules = sorted(set().union(*(cd.keys() for cd in cons_data.values())))
    for rule in all_cons_rules:
        row = f"| {rule} |"
        for c in conditions:
            val = cons_data[c].get(rule)
            row += f" {val:.0%} |" if val is not None else " N/A |"
        lines.append(row)
    lines.append("")

    # Raw trial data
    lines.append("## 4. 全試行データ")
    lines.append("")
    lines.append("| 条件 | Trial | ルール | LLM verdict | 正解 | 一致 |")
    lines.append("|------|-------|--------|------------|------|------|")

    for c in conditions:
        for t in sorted(summaries[c].trials, key=lambda x: (x.trial_id, x.rule_name)):
            mark = "OK" if t.is_correct else "NG"
            lines.append(
                f"| {c.value.upper()} | {t.trial_id} "
                f"| {t.rule_name[:35]} | {t.llm_verdict} "
                f"| {t.expected_verdict} | {mark} |"
            )
    lines.append("")

    # Conclusion
    lines.append("## 5. 考察")
    lines.append("")
    accs = {c: summaries[c].accuracy for c in conditions}
    best = max(accs, key=accs.get)  # type: ignore[arg-type]
    worst = min(accs, key=accs.get)  # type: ignore[arg-type]
    spread = accs[best] - accs[worst]

    lines.append(f"最高正答率は **{CONDITION_LABELS[best]}** ({accs[best]:.1%})、")
    lines.append(f"最低は **{CONDITION_LABELS[worst]}** ({accs[worst]:.1%})、")
    lines.append(f"差は {spread:.1%} であった。")
    lines.append("")

    # Per-condition analysis
    for cond in [Condition.MEMO, Condition.DOC]:
        if cond not in accs:
            continue
        label = CONDITION_LABELS[cond]
        cond_acc = accs[cond]
        rdf_acc = accs.get(Condition.RDF, 0)
        lines.append(f"### {label}条件について")
        lines.append("")
        diff = rdf_acc - cond_acc
        lines.append(f"RDF比で {diff:+.1%} の差。")
        if cond_acc < rdf_acc * 0.7:
            lines.append("構造化されていない記述ではLLMが因果関係や数値を正確に抽出しにくいことが示唆される。")
        elif cond_acc >= rdf_acc:
            lines.append("構造化形式と同等以上の精度が得られた。")
        else:
            lines.append("一定の精度は保てるものの、構造化形式には及ばない。")
        lines.append("")
    lines.append("")

    # Write
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text)
    print(f"Report generated: {REPORT_PATH}")
    return REPORT_PATH
