"""Generate the ontology effectiveness comparison report."""

from pathlib import Path

from ontoprobe.config import ROOT_DIR
from ontoprobe.evaluation.scorer import LevelSummary

REPORT_PATH = ROOT_DIR / "reports" / "ontology_effectiveness_report.md"

CAPABILITY_LABELS = {
    "hypothesis_generation": "仮説生成",
    "sql_accuracy": "SQL精度",
    "verdict_accuracy": "判定精度",
    "anomaly_detection": "異常検出",
    "actionability": "施策提案",
}


def generate_report(
    summaries: dict[int, LevelSummary],
    contributions: list[dict],
    level_contexts: dict[int, str],
    level_names: dict[int, str],
) -> Path:
    """Generate markdown report and write to file."""
    lines: list[str] = []

    # Title
    lines.append("# オントロジー記述の有効性検証レポート")
    lines.append("")
    lines.append("## 概要")
    lines.append("")
    lines.append("オントロジーの因果ルールを構成する各プロパティ（クラス階層、因果方向、")
    lines.append("期待値、条件、自然言語説明）が仮説検証の品質にどの程度寄与するかを")
    lines.append("段階的に評価した。6段階のレベル（L0-L5）で7つの仮説を検証し、")
    lines.append("5つの能力（仮説生成、SQL精度、判定精度、異常検出、施策提案）を")
    lines.append("0-2点でスコアリングした。")
    lines.append("")

    # Level definitions
    lines.append("## 評価レベル定義")
    lines.append("")
    lines.append("| Level | 含まれる情報 | 追加されるプロパティ |")
    lines.append("|-------|------------|-------------------|")
    additions = [
        "なし", "クラス階層 + メトリクスマッピング",
        "hasCause, hasEffect, hasDirection",
        "hasExpectedMagnitude", "hasCondition, hasComparedTo", "hasDescription",
    ]
    for level in range(6):
        lines.append(f"| {level_names[level]} | | {additions[level]} |")
    lines.append("")

    # Score summary table
    lines.append("## 1. レベル別スコアサマリ")
    lines.append("")
    lines.append("| Level | 仮説生成 | SQL精度 | 判定精度 | 異常検出 | 施策提案 | **合計** | **達成率** |")
    lines.append("|-------|---------|---------|---------|---------|---------|---------|----------|")

    for level in range(6):
        s = summaries[level]
        caps = s.by_capability
        pct = s.total / s.max_possible * 100
        lines.append(
            f"| {level_names[level].split(':')[0]} "
            f"| {caps['hypothesis_generation']}/14 "
            f"| {caps['sql_accuracy']}/14 "
            f"| {caps['verdict_accuracy']}/14 "
            f"| {caps['anomaly_detection']}/14 "
            f"| {caps['actionability']}/14 "
            f"| **{s.total}/70** "
            f"| **{pct:.0f}%** |"
        )
    lines.append("")

    # Marginal contribution
    lines.append("## 2. 限界貢献度（各レベル追加による改善）")
    lines.append("")
    lines.append("| 追加プロパティ | 合計改善 | 仮説生成 | SQL精度 | 判定精度 | 異常検出 | 施策提案 |")
    lines.append("|--------------|---------|---------|---------|---------|---------|---------|")

    property_labels = [
        "クラス階層+マッピング",
        "因果方向",
        "期待値",
        "条件・比較対象",
        "自然言語説明",
    ]
    for i, c in enumerate(contributions):
        d = c["capability_deltas"]
        lines.append(
            f"| L{c['from_level']}→L{c['to_level']}: {property_labels[i]} "
            f"| **+{c['total_delta']}** "
            f"| +{d['hypothesis_generation']} "
            f"| +{d['sql_accuracy']} "
            f"| +{d['verdict_accuracy']} "
            f"| +{d['anomaly_detection']} "
            f"| +{d['actionability']} |"
        )
    lines.append("")

    # Per-hypothesis detail
    lines.append("## 3. 仮説別の詳細分析")
    lines.append("")

    rule_names_ordered = [
        "Q4 revenue", "Discount volume", "VIP AOV",
        "Seasonal spike", "Free shipping", "Repeat CLV", "Discount margin",
    ]
    rule_labels = {
        "Q4 revenue": "Q4売上増（季節商品・年末効果）",
        "Discount volume": "割引キャンペーン→注文数増",
        "VIP AOV": "VIP顧客のAOV優位性",
        "Seasonal spike": "季節商品のQ4スパイク",
        "Free shipping": "送料無料→注文数増",
        "Repeat CLV": "リピート率とLTV相関",
        "Discount margin": "割引率とマージン低下",
    }

    for rule_name in rule_names_ordered:
        label = rule_labels[rule_name]
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Level | 仮説 | SQL | 判定 | 異常 | 施策 | 計 | 備考 |")
        lines.append("|-------|------|-----|------|------|------|----|------|")

        for level in range(6):
            scores = [
                s for s in summaries[level].scores if s.rule_name == rule_name
            ]
            if not scores:
                continue
            sc = scores[0]
            lines.append(
                f"| L{level} "
                f"| {sc.hypothesis_generation} "
                f"| {sc.sql_accuracy} "
                f"| {sc.verdict_accuracy} "
                f"| {sc.anomaly_detection} "
                f"| {sc.actionability} "
                f"| {sc.total} "
                f"| {sc.notes} |"
            )
        lines.append("")

    # Key findings
    lines.append("## 4. 主要な発見")
    lines.append("")

    # Calculate which level jump gives the biggest improvement
    max_contrib = max(contributions, key=lambda c: c["total_delta"])
    max_idx = contributions.index(max_contrib)

    lines.append(f"### 最大の効果: L{max_contrib['from_level']}→L{max_contrib['to_level']} ({property_labels[max_idx]})")
    lines.append("")
    lines.append(f"合計 **+{max_contrib['total_delta']}点** の改善。")
    lines.append("")

    # Analyze each transition
    lines.append("### プロパティ別の効果分析")
    lines.append("")

    lines.append("#### L0→L1: クラス階層 + メトリクスマッピング")
    lines.append("")
    lines.append("- **主な効果:** 仮説の方向付け（「何を調べるべきか」のヒント）")
    lines.append("- **限界:** 因果関係が不明なため「AとBに関係があるかも」レベルの仮説しか立てられない")
    lines.append("- クラス階層がないと、`is_seasonal`カラムの意味すら推測に頼る")
    lines.append("")

    lines.append("#### L1→L2: 因果方向（cause → effect + direction）")
    lines.append("")
    lines.append("- **主な効果:** 仮説生成とSQL精度が大幅改善")
    lines.append("- 「X→Yが増加する」と明示されることで、具体的で検証可能な仮説を立てられる")
    lines.append("- 判定も「方向が合っているか」までは可能に")
    lines.append("- **最もコストパフォーマンスの高いプロパティ**の候補")
    lines.append("")

    lines.append("#### L2→L3: 期待値（magnitude）")
    lines.append("")
    lines.append("- **主な効果:** 判定精度と異常検出が大幅改善")
    lines.append("- 期待値があることで「+7%は期待の15-30%より低い」「+601%は異常」と判定可能")
    lines.append("- **異常検出の鍵:** 期待値なしでは「多い/少ない」しか言えないが、期待値があれば「想定の何倍か」を定量評価")
    lines.append("- 施策提案も「期待に達していない」→「改善が必要」と根拠付けが可能に")
    lines.append("")

    lines.append("#### L3→L4: 条件・比較対象（condition, comparedTo）")
    lines.append("")
    lines.append("- **主な効果:** 一部仮説でSQL精度と施策提案が改善")
    lines.append("- `discount > 10%`の条件で検証範囲を限定し精度向上")
    lines.append("- `comparedTo: NewCustomer`で比較ベースラインを明示")
    lines.append("- **効果は仮説依存:** 条件が定義されている仮説でのみ改善（全仮説に効くわけではない）")
    lines.append("")

    lines.append("#### L4→L5: 自然言語説明（description）")
    lines.append("")
    lines.append("- **主な効果:** 施策提案の具体性が一部改善")
    lines.append("- 「冬物衣料・ギフト」のような背景情報で、商品カテゴリ別の深堀りが可能に")
    lines.append("- 「購買頻度ベースの分析に切り替え」のような代替アプローチを提案可能に")
    lines.append("- **改善幅は最も小さい:** 構造化プロパティ（L1-L4）が充実していれば追加効果は限定的")
    lines.append("")

    # Conclusion
    lines.append("## 5. 結論と推奨")
    lines.append("")
    lines.append("### 効果的なオントロジー記述の最小構成")
    lines.append("")
    lines.append("```")

    l3_summary = summaries[3]
    l5_summary = summaries[5]
    l3_pct = l3_summary.total / l3_summary.max_possible * 100
    l5_pct = l5_summary.total / l5_summary.max_possible * 100

    lines.append(f"L3（因果方向 + 期待値）で全体スコアの {l3_pct:.0f}% を達成")
    lines.append(f"L5（フルオントロジー）では {l5_pct:.0f}%")
    lines.append("```")
    lines.append("")
    lines.append("**最小有効構成は L3（クラス階層 + メトリクスマッピング + 因果方向 + 期待値）**")
    lines.append("")
    lines.append("この構成で仮説検証に必要な5能力の大部分をカバーできる。")
    lines.append("")
    lines.append("### プロパティの優先度")
    lines.append("")
    lines.append("| 優先度 | プロパティ | 効果 |")
    lines.append("|-------|-----------|------|")
    lines.append("| **必須** | クラス階層 + メトリクスマッピング | 仮説の対象を定義する基盤 |")
    lines.append("| **必須** | 因果方向（cause → effect + direction） | 検証可能な仮説を立てるために不可欠 |")
    lines.append("| **必須** | 期待値（magnitude） | 異常検出と判定精度の鍵 |")
    lines.append("| 推奨 | 条件・比較対象 | 検証精度向上（仮説依存） |")
    lines.append("| 任意 | 自然言語説明 | 施策提案の補強（LLM利用時に有効） |")
    lines.append("")
    lines.append("### 記述のコツ")
    lines.append("")
    lines.append("1. **期待値は具体的な数値範囲で記述する:** 「positive correlation」より「15-30%」の方が検証精度が高い")
    lines.append("2. **条件は検証可能な形で記述する:** 「seasonal」より「order_quarter = 4」の方がSQL生成に直結")
    lines.append("3. **比較対象を明示する:** 「AOVが高い」より「NewCustomerと比較して40-60%高い」の方が判定基準が明確")
    lines.append("4. **自然言語説明は構造化プロパティの補完に留める:** 説明だけでは検証不能、構造化データが先")
    lines.append("")

    # Write report
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(lines)
    REPORT_PATH.write_text(report_text)
    print(f"Report generated: {REPORT_PATH}")
    return REPORT_PATH
