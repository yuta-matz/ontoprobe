"""Score hypothesis verification quality at each ontology level.

Evaluates 5 capabilities on a 0-2 scale:
  - hypothesis_generation: Can a specific, testable hypothesis be formed?
  - sql_accuracy: Can the correct SQL query be derived?
  - verdict_accuracy: Can supported/contradicted be judged with degree?
  - anomaly_detection: Can unexpected deviations be flagged?
  - actionability: Can specific, evidence-based recommendations be made?
"""

from dataclasses import dataclass, field


@dataclass
class HypothesisScore:
    rule_name: str
    level: int
    hypothesis_generation: int  # 0-2
    sql_accuracy: int  # 0-2
    verdict_accuracy: int  # 0-2
    anomaly_detection: int  # 0-2
    actionability: int  # 0-2
    notes: str = ""

    @property
    def total(self) -> int:
        return (
            self.hypothesis_generation
            + self.sql_accuracy
            + self.verdict_accuracy
            + self.anomaly_detection
            + self.actionability
        )


@dataclass
class LevelSummary:
    level: int
    scores: list[HypothesisScore] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(s.total for s in self.scores)

    @property
    def max_possible(self) -> int:
        return len(self.scores) * 10  # 5 capabilities * 2 max each

    @property
    def by_capability(self) -> dict[str, int]:
        caps = [
            "hypothesis_generation",
            "sql_accuracy",
            "verdict_accuracy",
            "anomaly_detection",
            "actionability",
        ]
        return {cap: sum(getattr(s, cap) for s in self.scores) for cap in caps}


# Pre-defined scores for each rule at each level, based on analysis of what
# information is available and what can be derived from it.
#
# These scores encode the fundamental insight: what capability does each
# ontology property unlock?

SCORE_TABLE: list[HypothesisScore] = [
    # =========================================================================
    # Rule: Q4 has highest overall revenue
    # =========================================================================
    # L0: metadata has order_quarter, can GROUP BY, but no reason to expect Q4 > others
    HypothesisScore("Q4 revenue", 0, 0, 1, 0, 0, 0,
        "四半期別集計は可能だがQ4が高いという仮説を立てる根拠がない"),
    # L1: knows SeasonalProduct class exists, Revenue→total_revenue mapping
    HypothesisScore("Q4 revenue", 1, 1, 1, 0, 0, 0,
        "季節商品の概念を知るが因果方向が不明。漠然と「季節で差があるかも」程度"),
    # L2: knows SeasonalProduct → Revenue: increase
    HypothesisScore("Q4 revenue", 2, 2, 2, 1, 0, 0,
        "「季節商品が売上を押し上げる」と仮説を立てSQL生成可能。方向は判定できるが程度は不明"),
    # L3: knows magnitude 30-50%
    HypothesisScore("Q4 revenue", 3, 2, 2, 2, 1, 1,
        "+96%は期待値30-50%を超過していると判定可能。異常の方向は分かる"),
    # L4: knows condition order_quarter = 4
    HypothesisScore("Q4 revenue", 4, 2, 2, 2, 2, 1,
        "Q4に限定した検証が可能。+96%超過の異常度を定量評価できる"),
    # L5: full description adds "holiday season and year-end campaigns"
    HypothesisScore("Q4 revenue", 5, 2, 2, 2, 2, 2,
        "超過の原因候補（ホリデー需要+年末セール）を示し具体的改善提案が可能"),

    # =========================================================================
    # Rule: Discount increases order volume
    # =========================================================================
    HypothesisScore("Discount volume", 0, 0, 1, 0, 0, 0,
        "has_campaignで分割はできるが仮説の根拠なし"),
    HypothesisScore("Discount volume", 1, 1, 1, 0, 0, 0,
        "DiscountCampaignクラスを知るが効果の方向が不明"),
    HypothesisScore("Discount volume", 2, 2, 2, 1, 0, 0,
        "「割引→注文数増」の仮説とSQL生成可能。増減は判定できるが期待値なし"),
    HypothesisScore("Discount volume", 3, 2, 2, 2, 1, 1,
        "+7%が期待値15-30%を下回ると判定可能。改善の方向性を示せる"),
    HypothesisScore("Discount volume", 4, 2, 2, 2, 2, 2,
        "discount>10%の条件で絞り込み可能。期間・条件別の詳細分析と具体的改善策"),
    HypothesisScore("Discount volume", 5, 2, 2, 2, 2, 2,
        "L4と同等。説明文は追加情報が少ない"),

    # =========================================================================
    # Rule: VIP customers have higher AOV
    # =========================================================================
    HypothesisScore("VIP AOV", 0, 0, 1, 0, 0, 0,
        "customer_segmentで分割可能だが比較の仮説根拠なし"),
    HypothesisScore("VIP AOV", 1, 1, 1, 0, 0, 0,
        "VIPCustomer/NewCustomerクラスを知るがAOVとの関係不明"),
    HypothesisScore("VIP AOV", 2, 2, 2, 1, 0, 0,
        "「VIP→AOV増」の仮説でSQL生成可能。高いことは分かるが程度不明"),
    HypothesisScore("VIP AOV", 3, 2, 2, 2, 2, 1,
        "+601%が期待値40-60%を大幅超過と判定。明確な異常検出"),
    HypothesisScore("VIP AOV", 4, 2, 2, 2, 2, 2,
        "NewCustomerとの比較を明示的に指定。セグメント定義見直しの具体的提案"),
    HypothesisScore("VIP AOV", 5, 2, 2, 2, 2, 2,
        "L4と同等"),

    # =========================================================================
    # Rule: Seasonal products spike in Q4
    # =========================================================================
    HypothesisScore("Seasonal spike", 0, 0, 0, 0, 0, 0,
        "is_seasonalカラムの意味を推測する必要がありQ4との関連を仮説化できない"),
    HypothesisScore("Seasonal spike", 1, 1, 1, 0, 0, 0,
        "SeasonalProductクラスとSeasonalRevenue→seasonal_revenueマッピングを知る"),
    HypothesisScore("Seasonal spike", 2, 2, 2, 1, 0, 0,
        "「季節商品→季節売上増」の仮説+SQL。増加は分かるが規模不明"),
    HypothesisScore("Seasonal spike", 3, 2, 2, 2, 2, 1,
        "15倍が期待値2-3倍を大幅超過。データ生成パラメータの問題を指摘可能"),
    HypothesisScore("Seasonal spike", 4, 2, 2, 2, 2, 2,
        "Q4条件で限定検証。在庫計画の具体的提案が可能"),
    HypothesisScore("Seasonal spike", 5, 2, 2, 2, 2, 2,
        "「冬物衣料・ギフト」の説明で商品カテゴリ別の深堀り提案可能"),

    # =========================================================================
    # Rule: Free shipping increases order volume
    # =========================================================================
    HypothesisScore("Free shipping", 0, 0, 1, 0, 0, 0,
        "campaign_typeで分割可能だが効果の仮説根拠なし"),
    HypothesisScore("Free shipping", 1, 1, 1, 0, 0, 0,
        "FreeShippingCampaignクラスを知るが効果不明"),
    HypothesisScore("Free shipping", 2, 2, 2, 1, 0, 0,
        "「送料無料→注文数増」の仮説。-18%という逆の結果は分かるが評価基準なし"),
    HypothesisScore("Free shipping", 3, 2, 2, 2, 2, 1,
        "期待値+10-20%に対し-18%。明確な矛盾として検出。見直し提案可能"),
    HypothesisScore("Free shipping", 4, 2, 2, 2, 2, 2,
        "L3と同等（この仮説には条件・比較対象が定義されていない）"),
    HypothesisScore("Free shipping", 5, 2, 2, 2, 2, 2,
        "L4と同等"),

    # =========================================================================
    # Rule: Repeat purchases correlate with CLV
    # =========================================================================
    HypothesisScore("Repeat CLV", 0, 0, 0, 0, 0, 0,
        "total_ordersとlifetime_revenueの関係を仮説化する根拠なし"),
    HypothesisScore("Repeat CLV", 1, 1, 1, 0, 0, 0,
        "RepeatPurchaseRate, CLVの概念とメトリクスマッピングを知る"),
    HypothesisScore("Repeat CLV", 2, 1, 1, 1, 0, 0,
        "相関仮説は立てられるが全セグメント100%リピートで検証不能と判定"),
    HypothesisScore("Repeat CLV", 3, 1, 1, 1, 0, 0,
        "期待値「positive correlation」は漠然としており判定精度はL2と同等"),
    HypothesisScore("Repeat CLV", 4, 1, 1, 1, 0, 0,
        "条件・比較対象が未定義のためL3と同等"),
    HypothesisScore("Repeat CLV", 5, 1, 1, 1, 1, 1,
        "説明文から「購買頻度ベースの分析に切り替え」を提案可能"),

    # =========================================================================
    # Rule: Discounts reduce effective margin
    # =========================================================================
    HypothesisScore("Discount margin", 0, 0, 1, 0, 0, 0,
        "discount_amountカラムは見えるが因果仮説なし"),
    HypothesisScore("Discount margin", 1, 1, 1, 0, 0, 0,
        "DiscountCampaignとDiscountメトリクスの存在を知る"),
    HypothesisScore("Discount margin", 2, 2, 2, 1, 0, 0,
        "「割引→割引額増」の仮説+SQL。方向は判定可能"),
    HypothesisScore("Discount margin", 3, 2, 2, 2, 1, 1,
        "「discount_percentに比例」という期待値で線形性を検証可能"),
    HypothesisScore("Discount margin", 4, 2, 2, 2, 1, 1,
        "L3と同等（条件・比較対象が未定義）"),
    HypothesisScore("Discount margin", 5, 2, 2, 2, 2, 2,
        "説明文から「実質マージン低下」の観点で利益最適化の提案が可能"),
]


def get_scores_by_level() -> dict[int, LevelSummary]:
    """Get all scores grouped by level."""
    summaries: dict[int, LevelSummary] = {}
    for score in SCORE_TABLE:
        if score.level not in summaries:
            summaries[score.level] = LevelSummary(level=score.level)
        summaries[score.level].scores.append(score)
    return summaries


def get_marginal_contribution() -> list[dict]:
    """Calculate the marginal contribution of each level over the previous."""
    summaries = get_scores_by_level()
    contributions = []
    for level in range(1, 6):
        prev = summaries[level - 1]
        curr = summaries[level]
        delta = curr.total - prev.total
        prev_caps = prev.by_capability
        curr_caps = curr.by_capability
        cap_deltas = {cap: curr_caps[cap] - prev_caps[cap] for cap in curr_caps}
        contributions.append({
            "from_level": level - 1,
            "to_level": level,
            "total_delta": delta,
            "capability_deltas": cap_deltas,
        })
    return contributions
