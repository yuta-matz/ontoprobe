"""Generate ontology context at different detail levels for effectiveness comparison."""

from ontoprobe.ontology.query import CausalRule, MetricMapping

LEVEL_NAMES = {
    0: "L0: なし（メタデータ+セマンティックレイヤーのみ）",
    1: "L1: クラス階層 + メトリクスマッピング",
    2: "L2: + 因果方向（cause → effect + direction）",
    3: "L3: + 期待値（magnitude）",
    4: "L4: + 条件・比較対象（condition, comparedTo）",
    5: "L5: + 自然言語説明（description）= フルオントロジー",
}

CLASS_HIERARCHY = """\
### Class Hierarchy
- Customer → NewCustomer / ReturningCustomer / VIPCustomer
- Product → SeasonalProduct / EvergreenProduct
- Campaign → DiscountCampaign / FreeShippingCampaign
- Metric → RevenueMetric / VolumeMetric / CustomerMetric"""


def format_level_context(
    level: int,
    rules: list[CausalRule],
    mappings: list[MetricMapping],
) -> str:
    """Generate ontology context text for a given detail level.

    L0: empty
    L1: class hierarchy + metric mappings
    L2: + cause → effect + direction
    L3: + expected magnitude
    L4: + condition, comparedTo
    L5: + description (full)
    """
    if level == 0:
        return ""

    lines = ["## Domain Knowledge (Ontology)\n"]

    # L1: Class hierarchy + metric mappings
    lines.append(CLASS_HIERARCHY)
    lines.append("\n### Metric Mappings")
    for m in mappings:
        lines.append(f"  - {m.concept} → `{m.dbt_metric}`")

    if level == 1:
        return "\n".join(lines)

    # L2+: Causal rules
    lines.append("\n### Causal Rules")
    for i, rule in enumerate(rules, 1):
        lines.append(f"\n**Rule {i}: {rule.label}**")
        lines.append(f"  - Cause: {rule.cause}")
        lines.append(f"  - Effect on: {rule.effect}")
        lines.append(f"  - Direction: {rule.direction}")

        if level >= 3 and rule.magnitude:
            lines.append(f"  - Expected magnitude: {rule.magnitude}")

        if level >= 4:
            if rule.condition:
                lines.append(f"  - Condition: {rule.condition}")
            if rule.compared_to:
                lines.append(f"  - Compared to: {rule.compared_to}")

        if level >= 5:
            lines.append(f"  - {rule.description}")

    return "\n".join(lines)
