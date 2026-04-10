"""Generate markdown report for the multi-hop causal chain comparison experiment."""

from __future__ import annotations

from pathlib import Path

from ontoprobe.config import ROOT_DIR
from ontoprobe.evaluation.chain_comparison import ChainCondition, ChainConditionSummary

REPORT_PATH = ROOT_DIR / "reports" / "chain_comparison_report.md"

CONDITION_LABELS = {
    ChainCondition.RDF: "RDF（構造化）",
    ChainCondition.NL: "NL（自然言語）",
    ChainCondition.MEMO: "MEMO（社内文書）",
    ChainCondition.DOC: "DOC（議事録）",
}


def _fmt_acc(v: float) -> str:
    if v != v:  # NaN check
        return "N/A"
    return f"{v:.0%}"


def generate_chain_comparison_report(
    summaries: dict[ChainCondition, ChainConditionSummary],
    ground_truth: dict[str, str],
) -> Path:
    """Generate a markdown report for the chain comparison experiment."""
    lines: list[str] = []
    conditions = [c for c in ChainCondition if c in summaries]
    first = summaries[conditions[0]]

    # Header
    lines.append("# 多段階因果推論における知識記述形式の比較レポート")
    lines.append("")
    lines.append("## 概要")
    lines.append("")
    lines.append("多段階の因果連鎖（A→B→C）を含むドメイン知識を4つの異なる記述形式で")
    lines.append("LLMに渡した場合に、多段階推論の精度にどの程度の差が生じるかを検証した。")
    lines.append("")
    lines.append("### 比較条件")
    lines.append("")
    lines.append("| 条件 | 説明 |")
    lines.append("|------|------|")
    lines.append("| **RDF（構造化）** | RDF由来の箇条書き（全11ルール: 単段階7本＋多段階4本） |")
    lines.append("| **NL（自然言語）** | 同一情報を散文パラグラフで記述 |")
    lines.append("| **MEMO（社内文書）** | ルールごとに独立した社内文書で記述（多段階チェーン含む） |")
    lines.append("| **DOC（議事録）** | 1つの議事録に全ルール＋多段階因果の言及を埋め込み |")
    lines.append("")
    lines.append(f"- **試行回数:** 各条件 {first.num_trials} 回")
    lines.append(f"- **評価対象チェーン:** {len(ground_truth)} 件（多段階因果仮説のみ）")
    lines.append("- **Ground Truth:** デモモードのルールベース検証結果")
    lines.append("")

    # Ground truth
    lines.append("### Ground Truth（正解ラベル）")
    lines.append("")
    lines.append("| チェーン仮説 | 正解verdict |")
    lines.append("|-------------|-----------|")
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

    acc_row = "| verdict正答率 |"
    for c in conditions:
        acc_row += f" **{summaries[c].accuracy:.1%}** |"
    lines.append(acc_row)

    chain_row = "| 連鎖認識率 |"
    for c in conditions:
        chain_row += f" **{summaries[c].chain_awareness:.1%}** |"
    lines.append(chain_row)

    trial_row = "| 有効試行数 |"
    for c in conditions:
        trial_row += f" {len(summaries[c].trials)} |"
    lines.append(trial_row)

    cons_row = "| 平均一貫性 |"
    for c in conditions:
        s = summaries[c]
        avg = sum(s.consistency.values()) / len(s.consistency) if s.consistency else 0
        cons_row += f" {avg:.1%} |"
    lines.append(cons_row)
    lines.append("")

    # Per-rule accuracy
    lines.append("## 2. チェーン別正答率")
    lines.append("")
    header = "| チェーン仮説 | " + " | ".join(CONDITION_LABELS[c] for c in conditions) + " |"
    sep = "|-------------" + "|" + "|".join("---" for _ in conditions) + "|"
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

    # Chain awareness per rule
    lines.append("## 3. チェーン別 連鎖認識率")
    lines.append("")
    lines.append("LLMがverdict判定時に中間ステップ（因果の途中経路）に言及した割合。")
    lines.append("")
    header = "| チェーン仮説 | " + " | ".join(CONDITION_LABELS[c] for c in conditions) + " |"
    sep = "|-------------" + "|" + "|".join("---" for _ in conditions) + "|"
    lines.append(header)
    lines.append(sep)

    for rule in all_rules:
        row = f"| {rule} |"
        for c in conditions:
            trials = [t for t in summaries[c].trials if t.rule_name == rule]
            if trials:
                rate = sum(1 for t in trials if t.mentions_intermediate) / len(trials)
                row += f" {rate:.0%} |"
            else:
                row += " N/A |"
        lines.append(row)
    lines.append("")

    # Consistency per rule
    lines.append("## 4. チェーン別一貫性（verdict安定度）")
    lines.append("")
    header = "| チェーン仮説 | " + " | ".join(CONDITION_LABELS[c] for c in conditions) + " |"
    sep = "|-------------" + "|" + "|".join("---" for _ in conditions) + "|"
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
    lines.append("## 5. 全試行データ")
    lines.append("")
    lines.append("| 条件 | Trial | チェーン仮説 | LLM verdict | 正解 | 一致 | 連鎖認識 |")
    lines.append("|------|-------|-------------|------------|------|------|---------|")

    for c in conditions:
        for t in sorted(summaries[c].trials, key=lambda x: (x.trial_id, x.rule_name)):
            mark = "OK" if t.is_correct else "NG"
            chain_mark = "Yes" if t.mentions_intermediate else "No"
            lines.append(
                f"| {c.value.upper()} | {t.trial_id} "
                f"| {t.rule_name[:45]} | {t.llm_verdict} "
                f"| {t.expected_verdict} | {mark} | {chain_mark} |"
            )
    lines.append("")

    # Conclusion
    lines.append("## 6. 考察")
    lines.append("")

    accs = {c: summaries[c].accuracy for c in conditions}
    awareness = {c: summaries[c].chain_awareness for c in conditions}

    best_acc = max(accs, key=accs.get)  # type: ignore[arg-type]
    worst_acc = min(accs, key=accs.get)  # type: ignore[arg-type]
    spread = accs[best_acc] - accs[worst_acc]

    lines.append("### verdict正答率")
    lines.append("")
    lines.append(
        f"最高正答率は **{CONDITION_LABELS[best_acc]}** ({accs[best_acc]:.1%})、"
    )
    lines.append(
        f"最低は **{CONDITION_LABELS[worst_acc]}** ({accs[worst_acc]:.1%})、"
    )
    lines.append(f"差は {spread:.1%} であった。")
    lines.append("")

    # Structured vs unstructured comparison
    structured_avg = (accs.get(ChainCondition.RDF, 0) + accs.get(ChainCondition.NL, 0)) / 2
    unstructured_avg = (accs.get(ChainCondition.MEMO, 0) + accs.get(ChainCondition.DOC, 0)) / 2
    lines.append(
        f"構造化条件（RDF+NL）の平均正答率: {structured_avg:.1%}、"
        f"非構造化条件（MEMO+DOC）の平均正答率: {unstructured_avg:.1%}。"
    )
    if structured_avg > unstructured_avg:
        diff = structured_avg - unstructured_avg
        lines.append(
            f"多段階因果推論では構造化された知識提供が **{diff:.1%}** 優位。"
        )
    elif unstructured_avg > structured_avg:
        diff = unstructured_avg - structured_avg
        lines.append(
            f"非構造化条件が **{diff:.1%}** 上回った。"
        )
    else:
        lines.append("構造化・非構造化で差は見られなかった。")
    lines.append("")

    # Chain awareness analysis
    lines.append("### 連鎖認識率")
    lines.append("")
    best_aware = max(awareness, key=awareness.get)  # type: ignore[arg-type]
    worst_aware = min(awareness, key=awareness.get)  # type: ignore[arg-type]
    lines.append(
        f"最高連鎖認識率は **{CONDITION_LABELS[best_aware]}** ({awareness[best_aware]:.1%})、"
    )
    lines.append(
        f"最低は **{CONDITION_LABELS[worst_aware]}** ({awareness[worst_aware]:.1%})。"
    )
    lines.append("")

    structured_aware = (awareness.get(ChainCondition.RDF, 0) + awareness.get(ChainCondition.NL, 0)) / 2
    unstructured_aware = (awareness.get(ChainCondition.MEMO, 0) + awareness.get(ChainCondition.DOC, 0)) / 2
    lines.append(
        f"構造化条件の平均連鎖認識率: {structured_aware:.1%}、"
        f"非構造化条件: {unstructured_aware:.1%}。"
    )
    lines.append("")

    # Per-condition notes
    lines.append("### 条件別分析")
    lines.append("")
    rdf_acc = accs.get(ChainCondition.RDF, 0)
    for cond in conditions:
        label = CONDITION_LABELS[cond]
        cond_acc = accs[cond]
        cond_aware = awareness[cond]
        lines.append(f"- **{label}**: 正答率 {cond_acc:.1%}、連鎖認識率 {cond_aware:.1%}")
        if cond == ChainCondition.MEMO and cond_acc < rdf_acc * 0.7:
            lines.append(
                "  - 断片化された文書では多段階因果の認識が困難であることが示唆される"
            )
        if cond == ChainCondition.DOC and cond_acc < rdf_acc * 0.7:
            lines.append(
                "  - 議事録のノイズが多段階推論を阻害している可能性がある"
            )
    lines.append("")

    # Summary
    lines.append("### 総括")
    lines.append("")
    lines.append("多段階因果推論（A→B→C）における知識記述形式の影響:")
    lines.append("")
    if spread > 0.2:
        lines.append(
            "記述形式によって大きな精度差が確認された。"
            "多段階の因果連鎖はLLMにとって認知負荷が高く、"
            "知識の構造化が単段階ルール以上に重要であることが示唆される。"
        )
    elif spread > 0.1:
        lines.append(
            "記述形式による中程度の精度差が確認された。"
            "多段階因果は単段階よりも形式の影響を受けやすい傾向がある。"
        )
    else:
        lines.append(
            "記述形式による精度差は小さかった。"
            "現在の規模（3チェーン仮説）ではLLMは形式を問わず"
            "多段階因果を推論できている可能性がある。"
        )
    lines.append("")

    # Write
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text)
    print(f"Report generated: {REPORT_PATH}")
    return REPORT_PATH
