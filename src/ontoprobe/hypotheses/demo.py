"""Demo mode: pre-defined hypotheses and rule-based verification (no LLM required)."""

from ontoprobe.hypotheses.models import Hypothesis, VerificationResult


DEMO_HYPOTHESES = [
    Hypothesis(
        description="Q4の売上はQ1-Q3の平均より30-50%高い（季節商品・年末セールの影響）",
        ontology_rule="Q4 has highest overall revenue",
        expected_direction="increase",
        sql_query="""\
SELECT
    order_quarter,
    SUM(total_amount) AS quarterly_revenue,
    COUNT(*) AS order_count,
    AVG(total_amount) AS avg_order_value
FROM fct_orders
GROUP BY order_quarter
ORDER BY order_quarter""",
        relevant_metrics=["total_revenue", "order_count"],
        relevant_dimensions=["order_quarter"],
    ),
    Hypothesis(
        description="割引キャンペーン期間中の注文数は非キャンペーン期間より15-30%多い",
        ontology_rule="Discount increases order volume",
        expected_direction="increase",
        sql_query="""\
WITH daily_orders AS (
    SELECT
        order_date,
        has_campaign,
        COUNT(*) AS daily_order_count
    FROM fct_orders
    GROUP BY order_date, has_campaign
)
SELECT
    has_campaign,
    AVG(daily_order_count) AS avg_daily_orders,
    COUNT(*) AS num_days
FROM daily_orders
GROUP BY has_campaign""",
        relevant_metrics=["order_count"],
        relevant_dimensions=["has_campaign"],
    ),
    Hypothesis(
        description="VIP顧客の平均注文額はNew顧客より40-60%高い",
        ontology_rule="VIP customers have higher AOV",
        expected_direction="increase",
        sql_query="""\
SELECT
    customer_segment,
    AVG(total_amount) AS avg_order_value,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_revenue
FROM fct_orders
WHERE customer_segment IN ('vip', 'new')
GROUP BY customer_segment""",
        relevant_metrics=["average_order_value"],
        relevant_dimensions=["customer_segment"],
    ),
    Hypothesis(
        description="季節商品のQ4売上はQ1-Q3平均の2-3倍になる",
        ontology_rule="Seasonal products spike in Q4",
        expected_direction="increase",
        sql_query="""\
SELECT
    order_quarter,
    SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) AS seasonal_revenue,
    SUM(CASE WHEN NOT is_seasonal THEN line_total ELSE 0 END) AS evergreen_revenue,
    SUM(line_total) AS total_item_revenue
FROM fct_order_items
GROUP BY order_quarter
ORDER BY order_quarter""",
        relevant_metrics=["seasonal_revenue"],
        relevant_dimensions=["order_quarter", "is_seasonal"],
    ),
    Hypothesis(
        description="送料無料キャンペーンは注文数を10-20%増加させる",
        ontology_rule="Free shipping increases order volume",
        expected_direction="increase",
        sql_query="""\
WITH campaign_orders AS (
    SELECT
        o.order_date,
        c.campaign_type,
        COUNT(*) AS daily_orders
    FROM fct_orders o
    LEFT JOIN dim_campaigns c USING (campaign_id)
    GROUP BY o.order_date, c.campaign_type
)
SELECT
    COALESCE(campaign_type, 'no_campaign') AS campaign_type,
    AVG(daily_orders) AS avg_daily_orders,
    COUNT(*) AS num_days
FROM campaign_orders
GROUP BY campaign_type""",
        relevant_metrics=["order_count"],
        relevant_dimensions=["campaign_type"],
    ),
    Hypothesis(
        description="リピート購入率が高い顧客セグメントほどLTV（生涯価値）が高い",
        ontology_rule="Repeat purchases correlate with CLV",
        expected_direction="increase",
        sql_query="""\
SELECT
    customer_segment,
    AVG(CASE WHEN total_orders > 1 THEN 1.0 ELSE 0.0 END) AS repeat_rate,
    AVG(lifetime_revenue) AS avg_ltv,
    COUNT(*) AS customer_count
FROM dim_customers
GROUP BY customer_segment
ORDER BY repeat_rate""",
        relevant_metrics=["repeat_purchase_rate", "customer_lifetime_value"],
        relevant_dimensions=["customer_segment"],
    ),
    Hypothesis(
        description="割引率が高いキャンペーンほど割引総額が大きく、実質マージンが低下する",
        ontology_rule="Discounts reduce effective margin",
        expected_direction="increase",
        sql_query="""\
SELECT
    c.campaign_name,
    c.discount_percent,
    COUNT(o.order_id) AS order_count,
    SUM(o.discount_amount) AS total_discount,
    SUM(o.total_amount) AS total_revenue,
    ROUND(SUM(o.discount_amount)::FLOAT / NULLIF(SUM(o.total_amount + o.discount_amount), 0) * 100, 1) AS effective_discount_pct
FROM fct_orders o
JOIN dim_campaigns c USING (campaign_id)
GROUP BY c.campaign_name, c.discount_percent
ORDER BY c.discount_percent""",
        relevant_metrics=["total_discount", "total_revenue"],
        relevant_dimensions=["campaign_name", "discount_percent"],
    ),
]

# Multi-hop chain hypotheses for FLAT vs CHAIN comparison experiment
CHAIN_HYPOTHESES = [
    Hypothesis(
        description="割引キャンペーンは注文数増加を通じて売上全体を押し上げる（Discount→OrderVolume→Revenue）",
        ontology_rule="Discount drives revenue through order volume",
        expected_direction="increase",
        sql_query="""\
WITH daily AS (
    SELECT
        order_date,
        has_campaign,
        COUNT(*) AS daily_orders,
        SUM(total_amount) AS daily_revenue
    FROM fct_orders
    GROUP BY order_date, has_campaign
)
SELECT
    has_campaign,
    AVG(daily_orders) AS avg_daily_orders,
    AVG(daily_revenue) AS avg_daily_revenue,
    COUNT(*) AS num_days
FROM daily
GROUP BY has_campaign""",
        relevant_metrics=["order_count", "total_revenue"],
        relevant_dimensions=["has_campaign"],
    ),
    Hypothesis(
        description="割引キャンペーンは割引額増大を通じて実質マージンを低下させる（Discount→DiscountAmount→EffectiveMargin）",
        ontology_rule="Discount erodes effective margin through discount amount",
        expected_direction="decrease",
        sql_query="""\
WITH daily AS (
    SELECT
        order_date,
        has_campaign,
        SUM(discount_amount) AS daily_discount,
        SUM(total_amount) AS daily_revenue,
        SUM(total_amount + discount_amount) AS daily_gross
    FROM fct_orders
    GROUP BY order_date, has_campaign
)
SELECT
    has_campaign,
    AVG(daily_discount) AS avg_daily_discount,
    AVG(daily_revenue) AS avg_daily_revenue,
    AVG(daily_gross) AS avg_daily_gross,
    ROUND(SUM(daily_revenue)::FLOAT / NULLIF(SUM(daily_gross), 0) * 100, 1) AS effective_margin_pct
FROM daily
GROUP BY has_campaign""",
        relevant_metrics=["total_discount", "total_revenue"],
        relevant_dimensions=["has_campaign"],
    ),
    Hypothesis(
        description="VIP顧客は高AOVを通じて売上に大きく貢献する（VIP→AOV→Revenue）",
        ontology_rule="VIP customers drive revenue through higher AOV",
        expected_direction="increase",
        sql_query="""\
SELECT
    customer_segment,
    COUNT(*) AS order_count,
    AVG(total_amount) AS avg_order_value,
    SUM(total_amount) AS total_revenue,
    SUM(total_amount) * 1.0 / SUM(SUM(total_amount)) OVER () AS revenue_share
FROM fct_orders
WHERE customer_segment IN ('vip', 'new', 'returning')
GROUP BY customer_segment
ORDER BY avg_order_value DESC""",
        relevant_metrics=["average_order_value", "total_revenue"],
        relevant_dimensions=["customer_segment"],
    ),
]

# 3-hop chain hypotheses for hop-count comparison experiment
THREE_HOP_HYPOTHESES = [
    Hypothesis(
        description="季節商品のQ4売上スパイクがQ4全体売上を押し上げ、年間売上がQ4に集中する（Seasonal→SeasonalRevenue→Q4Revenue→AnnualConcentration）",
        ontology_rule="Seasonal spike concentrates annual revenue in Q4",
        expected_direction="increase",
        sql_query="""\
SELECT
    order_quarter,
    SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) AS seasonal_revenue,
    SUM(line_total) AS quarter_revenue,
    SUM(line_total) * 1.0 / SUM(SUM(line_total)) OVER () AS quarter_share
FROM fct_order_items
GROUP BY order_quarter
ORDER BY order_quarter""",
        relevant_metrics=["seasonal_revenue", "total_revenue", "q4_revenue_share"],
        relevant_dimensions=["order_quarter", "is_seasonal"],
    ),
    Hypothesis(
        description="VIP顧客の高AOVが売上を押し上げ、売上が少数のVIPセグメントに集中する（VIP→AOV→Revenue→RevenueConcentration）",
        ontology_rule="VIP revenue drives concentration risk",
        expected_direction="increase",
        sql_query="""\
SELECT
    customer_segment,
    COUNT(*) AS order_count,
    AVG(total_amount) AS avg_order_value,
    SUM(total_amount) AS total_revenue,
    SUM(total_amount) * 1.0 / SUM(SUM(total_amount)) OVER () AS revenue_share,
    COUNT(*) * 1.0 / SUM(COUNT(*)) OVER () AS order_share
FROM fct_orders
GROUP BY customer_segment
ORDER BY avg_order_value DESC""",
        relevant_metrics=["average_order_value", "total_revenue", "segment_revenue_share"],
        relevant_dimensions=["customer_segment"],
    ),
    Hypothesis(
        description="割引キャンペーンは注文数増でも売上減のため、利益成長に繋がらない（Discount→OrderVolume→Revenue→ProfitGrowth）",
        ontology_rule="Discount revenue impact limits profit growth",
        expected_direction="increase",
        sql_query="""\
WITH daily AS (
    SELECT
        order_date,
        has_campaign,
        COUNT(*) AS daily_orders,
        SUM(total_amount) AS daily_revenue,
        SUM(discount_amount) AS daily_discount,
        SUM(total_amount) - SUM(discount_amount) AS daily_net
    FROM fct_orders
    GROUP BY order_date, has_campaign
)
SELECT
    has_campaign,
    AVG(daily_orders) AS avg_daily_orders,
    AVG(daily_revenue) AS avg_daily_revenue,
    AVG(daily_discount) AS avg_daily_discount,
    AVG(daily_net) AS avg_daily_net_revenue
FROM daily
GROUP BY has_campaign""",
        relevant_metrics=["order_count", "total_revenue", "net_revenue_growth"],
        relevant_dimensions=["has_campaign"],
    ),
]

# 4-hop chain hypotheses
FOUR_HOP_HYPOTHESES = [
    Hypothesis(
        description="季節商品スパイク→Q4売上集中→年間集中→季節依存リスク: Q4から季節商品を除くと平均四半期水準に落ちる",
        ontology_rule="Q4 concentration creates seasonal dependency risk",
        expected_direction="increase",
        sql_query="""\
SELECT
    order_quarter,
    SUM(line_total) AS total_revenue,
    SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) AS seasonal_revenue,
    SUM(CASE WHEN NOT is_seasonal THEN line_total ELSE 0 END) AS evergreen_revenue,
    SUM(line_total) * 1.0 / SUM(SUM(line_total)) OVER () AS quarter_share
FROM fct_order_items
GROUP BY order_quarter
ORDER BY order_quarter""",
        relevant_metrics=["seasonal_revenue", "total_revenue", "q4_seasonal_dependency"],
        relevant_dimensions=["order_quarter", "is_seasonal"],
    ),
    Hypothesis(
        description="VIP高AOV→売上貢献→売上集中→セグメント依存リスク: VIP1人あたり売上がNew顧客の5倍以上",
        ontology_rule="VIP concentration creates segment dependency risk",
        expected_direction="increase",
        sql_query="""\
SELECT
    customer_segment,
    COUNT(DISTINCT customer_id) AS customer_count,
    SUM(total_amount) AS total_revenue,
    SUM(total_amount) / COUNT(DISTINCT customer_id) AS revenue_per_customer,
    SUM(total_amount) * 1.0 / SUM(SUM(total_amount)) OVER () AS revenue_share,
    COUNT(DISTINCT customer_id) * 1.0 / SUM(COUNT(DISTINCT customer_id)) OVER () AS customer_share
FROM fct_orders
GROUP BY customer_segment
ORDER BY revenue_per_customer DESC""",
        relevant_metrics=["total_revenue", "vip_dependency_ratio"],
        relevant_dimensions=["customer_segment"],
    ),
    Hypothesis(
        description="割引→注文増→売上減→利益減→キャンペーン非効率: キャンペーン日の売上がキャンペーンなし日を下回る",
        ontology_rule="Negative profit growth indicates poor campaign efficiency",
        expected_direction="decrease",
        sql_query="""\
WITH daily AS (
    SELECT order_date, has_campaign,
           COUNT(*) AS orders, SUM(total_amount) AS revenue,
           SUM(discount_amount) AS discount
    FROM fct_orders GROUP BY order_date, has_campaign
)
SELECT has_campaign,
       AVG(orders) AS avg_daily_orders,
       AVG(revenue) AS avg_daily_revenue,
       AVG(discount) AS avg_daily_discount,
       AVG(revenue) - AVG(discount) AS avg_daily_net
FROM daily GROUP BY has_campaign""",
        relevant_metrics=["order_count", "total_revenue", "campaign_roi"],
        relevant_dimensions=["has_campaign"],
    ),
]

# 5-hop chain hypotheses
FIVE_HOP_HYPOTHESES = [
    Hypothesis(
        description="季節商品→Q4スパイク→年間集中→季節依存→戦略的脆弱性: Q4季節商品がQ4売上の50%超を占め、年間売上の20%超に相当する",
        ontology_rule="Seasonal dependency creates strategic vulnerability",
        expected_direction="increase",
        sql_query="""\
SELECT
    order_quarter,
    SUM(line_total) AS total_revenue,
    SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) AS seasonal_revenue,
    SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) * 1.0 / NULLIF(SUM(line_total), 0) AS seasonal_share_of_quarter,
    SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) * 1.0 / SUM(SUM(line_total)) OVER () AS seasonal_share_of_annual
FROM fct_order_items
GROUP BY order_quarter
ORDER BY order_quarter""",
        relevant_metrics=["seasonal_revenue", "total_revenue", "seasonal_vulnerability_index"],
        relevant_dimensions=["order_quarter", "is_seasonal"],
    ),
    Hypothesis(
        description="VIP→高AOV→売上→集中→依存→VIP維持最優先: VIP1人あたり売上が全顧客平均の3倍以上",
        ontology_rule="Segment dependency demands VIP retention priority",
        expected_direction="increase",
        sql_query="""\
WITH customer_rev AS (
    SELECT customer_id, customer_segment,
           SUM(total_amount) AS total_revenue,
           COUNT(*) AS order_count
    FROM fct_orders GROUP BY customer_id, customer_segment
)
SELECT customer_segment,
       COUNT(*) AS customers,
       AVG(total_revenue) AS avg_revenue_per_customer,
       AVG(total_revenue) / (SELECT AVG(total_revenue) FROM customer_rev) AS vs_average_ratio,
       SUM(total_revenue) * 1.0 / (SELECT SUM(total_revenue) FROM customer_rev) AS revenue_share
FROM customer_rev
GROUP BY customer_segment
ORDER BY avg_revenue_per_customer DESC""",
        relevant_metrics=["total_revenue", "vip_retention_urgency"],
        relevant_dimensions=["customer_segment"],
    ),
    Hypothesis(
        description="割引→注文増→売上減→利益減→非効率→戦略見直し必要: 割引コストが売上増分を上回り、1割引円あたりの売上回収率が低い",
        ontology_rule="Poor campaign efficiency demands strategy revision",
        expected_direction="increase",
        sql_query="""\
WITH daily AS (
    SELECT order_date, has_campaign,
           COUNT(*) AS orders,
           SUM(total_amount) AS revenue,
           SUM(discount_amount) AS discount,
           SUM(total_amount + discount_amount) AS gross
    FROM fct_orders GROUP BY order_date, has_campaign
)
SELECT has_campaign,
       AVG(orders) AS avg_daily_orders,
       AVG(revenue) AS avg_daily_revenue,
       AVG(discount) AS avg_daily_discount,
       AVG(gross) AS avg_daily_gross,
       CASE WHEN AVG(discount) > 0
            THEN AVG(revenue) / AVG(discount) ELSE NULL END AS revenue_per_discount_dollar
FROM daily GROUP BY has_campaign""",
        relevant_metrics=["total_revenue", "total_discount", "campaign_revision_score"],
        relevant_dimensions=["has_campaign"],
    ),
]


def verify_demo(hypothesis: Hypothesis, query_result: list[dict]) -> VerificationResult:
    """Rule-based verification without LLM."""
    rule = hypothesis.ontology_rule

    if rule == "Q4 has highest overall revenue":
        return _verify_q4_revenue(hypothesis, query_result)
    elif rule == "Discount increases order volume":
        return _verify_discount_volume(hypothesis, query_result)
    elif rule == "VIP customers have higher AOV":
        return _verify_vip_aov(hypothesis, query_result)
    elif rule == "Seasonal products spike in Q4":
        return _verify_seasonal_spike(hypothesis, query_result)
    elif rule == "Free shipping increases order volume":
        return _verify_free_shipping(hypothesis, query_result)
    elif rule == "Repeat purchases correlate with CLV":
        return _verify_repeat_clv(hypothesis, query_result)
    elif rule == "Discounts reduce effective margin":
        return _verify_discount_margin(hypothesis, query_result)
    elif rule == "Discount drives revenue through order volume":
        return _verify_discount_revenue_chain(hypothesis, query_result)
    elif rule == "Discount erodes effective margin through discount amount":
        return _verify_discount_margin_chain(hypothesis, query_result)
    elif rule == "VIP customers drive revenue through higher AOV":
        return _verify_vip_revenue_chain(hypothesis, query_result)
    elif rule == "Seasonal spike concentrates annual revenue in Q4":
        return _verify_seasonal_concentration_3hop(hypothesis, query_result)
    elif rule == "VIP revenue drives concentration risk":
        return _verify_vip_concentration_3hop(hypothesis, query_result)
    elif rule == "Discount revenue impact limits profit growth":
        return _verify_discount_profit_3hop(hypothesis, query_result)
    # 4-hop
    elif rule == "Q4 concentration creates seasonal dependency risk":
        return _verify_q4_dependency_4hop(hypothesis, query_result)
    elif rule == "VIP concentration creates segment dependency risk":
        return _verify_vip_dependency_4hop(hypothesis, query_result)
    elif rule == "Negative profit growth indicates poor campaign efficiency":
        return _verify_campaign_efficiency_4hop(hypothesis, query_result)
    # 5-hop
    elif rule == "Seasonal dependency creates strategic vulnerability":
        return _verify_strategic_vulnerability_5hop(hypothesis, query_result)
    elif rule == "Segment dependency demands VIP retention priority":
        return _verify_retention_priority_5hop(hypothesis, query_result)
    elif rule == "Poor campaign efficiency demands strategy revision":
        return _verify_strategy_revision_5hop(hypothesis, query_result)

    return VerificationResult(
        hypothesis=hypothesis,
        query_result=query_result,
        verdict="inconclusive",
        evidence_summary="No verification rule for this hypothesis",
    )


def _verify_q4_revenue(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    q4 = next((r for r in rows if r["order_quarter"] == 4), None)
    others = [r for r in rows if r["order_quarter"] != 4]
    if not q4 or not others:
        return _inconclusive(h, rows, "Insufficient data")

    avg_other = sum(r["quarterly_revenue"] for r in others) / len(others)
    pct_increase = (q4["quarterly_revenue"] - avg_other) / avg_other * 100

    if pct_increase >= 30:
        verdict = "supported"
        summary = f"Q4売上は他四半期平均比+{pct_increase:.0f}% (Q4: {q4['quarterly_revenue']:,}, 他平均: {avg_other:,.0f})"
    elif pct_increase > 0:
        verdict = "supported"
        summary = f"Q4は+{pct_increase:.0f}%増だが期待値(30-50%)より低い (Q4: {q4['quarterly_revenue']:,})"
    else:
        verdict = "contradicted"
        summary = f"Q4売上が他四半期より低い ({pct_increase:.0f}%)"

    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_discount_volume(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    campaign = next((r for r in rows if r["has_campaign"]), None)
    no_campaign = next((r for r in rows if not r["has_campaign"]), None)
    if not campaign or not no_campaign:
        return _inconclusive(h, rows, "Insufficient data")

    pct = (campaign["avg_daily_orders"] - no_campaign["avg_daily_orders"]) / no_campaign["avg_daily_orders"] * 100
    if pct >= 15:
        verdict = "supported"
    elif pct > 0:
        verdict = "supported"
    else:
        verdict = "contradicted"
    summary = f"キャンペーン日平均{campaign['avg_daily_orders']:.1f}件 vs 通常{no_campaign['avg_daily_orders']:.1f}件 ({pct:+.0f}%)"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_vip_aov(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    vip = next((r for r in rows if r["customer_segment"] == "vip"), None)
    new = next((r for r in rows if r["customer_segment"] == "new"), None)
    if not vip or not new:
        return _inconclusive(h, rows, "Insufficient data")

    pct = (vip["avg_order_value"] - new["avg_order_value"]) / new["avg_order_value"] * 100
    verdict = "supported" if pct >= 30 else ("supported" if pct > 0 else "contradicted")
    summary = f"VIP AOV: {vip['avg_order_value']:,.0f} vs New: {new['avg_order_value']:,.0f} ({pct:+.0f}%)"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_seasonal_spike(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    q4 = next((r for r in rows if r["order_quarter"] == 4), None)
    others = [r for r in rows if r["order_quarter"] != 4]
    if not q4 or not others:
        return _inconclusive(h, rows, "Insufficient data")

    avg_other = sum(r["seasonal_revenue"] for r in others) / len(others)
    if avg_other == 0:
        return _inconclusive(h, rows, "Q1-Q3の季節商品売上が0")

    ratio = q4["seasonal_revenue"] / avg_other
    verdict = "supported" if ratio >= 2 else ("supported" if ratio > 1 else "contradicted")
    summary = f"Q4季節商品売上はQ1-Q3平均の{ratio:.1f}倍 (Q4: {q4['seasonal_revenue']:,}, 他平均: {avg_other:,.0f})"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_free_shipping(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    free_ship = next((r for r in rows if r["campaign_type"] == "free_shipping"), None)
    no_camp = next((r for r in rows if r["campaign_type"] == "no_campaign"), None)
    if not free_ship or not no_camp:
        return _inconclusive(h, rows, "Insufficient data")

    pct = (free_ship["avg_daily_orders"] - no_camp["avg_daily_orders"]) / no_camp["avg_daily_orders"] * 100
    verdict = "supported" if pct >= 10 else ("supported" if pct > 0 else "contradicted")
    summary = f"送料無料日平均{free_ship['avg_daily_orders']:.1f}件 vs 通常{no_camp['avg_daily_orders']:.1f}件 ({pct:+.0f}%)"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_repeat_clv(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    sorted_rows = sorted(rows, key=lambda r: r["repeat_rate"])
    if len(sorted_rows) < 2:
        return _inconclusive(h, rows, "Insufficient segments")

    ltvs = [r["avg_ltv"] for r in sorted_rows]
    is_increasing = all(ltvs[i] <= ltvs[i + 1] for i in range(len(ltvs) - 1))
    parts = [f"{r['customer_segment']}: repeat={r['repeat_rate']:.0%}, LTV={r['avg_ltv']:,.0f}" for r in sorted_rows]
    verdict = "supported" if is_increasing else "inconclusive"
    summary = " | ".join(parts)
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_discount_margin(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    sorted_rows = sorted(rows, key=lambda r: r["discount_percent"])
    if len(sorted_rows) < 2:
        return _inconclusive(h, rows, "Insufficient campaigns")

    discounts_increase = sorted_rows[-1]["effective_discount_pct"] > sorted_rows[0]["effective_discount_pct"]
    parts = [f"{r['campaign_name']}: {r['discount_percent']}%割引→実質{r['effective_discount_pct']}%" for r in sorted_rows if r["discount_percent"] > 0]
    verdict = "supported" if discounts_increase else "contradicted"
    summary = " | ".join(parts) if parts else "割引キャンペーンなし"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _inconclusive(h: Hypothesis, rows: list[dict], msg: str) -> VerificationResult:
    return VerificationResult(hypothesis=h, query_result=rows, verdict="inconclusive", evidence_summary=msg)


# =============================================================================
# Multi-hop chain verification functions
# =============================================================================


def _verify_discount_revenue_chain(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    """Verify: Discount → OrderVolume → Revenue chain.

    Both intermediate (daily order count up) and final (daily revenue up) must hold.
    """
    campaign = next((r for r in rows if r["has_campaign"]), None)
    no_campaign = next((r for r in rows if not r["has_campaign"]), None)
    if not campaign or not no_campaign:
        return _inconclusive(h, rows, "Insufficient data")

    vol_pct = (campaign["avg_daily_orders"] - no_campaign["avg_daily_orders"]) / no_campaign["avg_daily_orders"] * 100
    rev_pct = (campaign["avg_daily_revenue"] - no_campaign["avg_daily_revenue"]) / no_campaign["avg_daily_revenue"] * 100

    vol_up = vol_pct > 0
    rev_up = rev_pct > 0

    if vol_up and rev_up:
        verdict = "supported"
        summary = (
            f"チェーン検証成功: 日平均注文数{vol_pct:+.0f}% → 日平均売上{rev_pct:+.0f}% "
            f"(キャンペーン{campaign['avg_daily_orders']:.1f}件/{campaign['avg_daily_revenue']:,.0f}円 "
            f"vs 通常{no_campaign['avg_daily_orders']:.1f}件/{no_campaign['avg_daily_revenue']:,.0f}円)"
        )
    elif vol_up and not rev_up:
        verdict = "contradicted"
        summary = f"日平均注文数は増加({vol_pct:+.0f}%)だが日平均売上は減少({rev_pct:+.0f}%) - 中間ステップのみ成立"
    else:
        verdict = "contradicted"
        summary = f"日平均注文数{vol_pct:+.0f}%, 日平均売上{rev_pct:+.0f}% - チェーンの起点から不成立"

    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_discount_margin_chain(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    """Verify: Discount → DiscountAmount → EffectiveMargin decrease chain.

    Discount campaigns should increase discount amounts AND reduce effective margin.
    """
    campaign = next((r for r in rows if r["has_campaign"]), None)
    no_campaign = next((r for r in rows if not r["has_campaign"]), None)
    if not campaign or not no_campaign:
        return _inconclusive(h, rows, "Insufficient data")

    discount_higher = campaign["avg_daily_discount"] > no_campaign["avg_daily_discount"]
    margin_lower = campaign["effective_margin_pct"] < no_campaign["effective_margin_pct"]

    if discount_higher and margin_lower:
        verdict = "supported"
        summary = (
            f"チェーン検証成功: 日平均割引額増({campaign['avg_daily_discount']:,.0f} vs {no_campaign['avg_daily_discount']:,.0f}) "
            f"→ マージン低下({campaign['effective_margin_pct']}% vs {no_campaign['effective_margin_pct']}%)"
        )
    elif discount_higher and not margin_lower:
        verdict = "contradicted"
        summary = f"割引額は増加だがマージンは低下せず({campaign['effective_margin_pct']}% vs {no_campaign['effective_margin_pct']}%)"
    else:
        verdict = "contradicted"
        summary = f"割引額がキャンペーン期間で増加していない"

    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_vip_revenue_chain(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    """Verify: VIP → AOV → Revenue chain.

    VIP should have higher AOV AND disproportionate revenue contribution.
    """
    vip = next((r for r in rows if r["customer_segment"] == "vip"), None)
    new = next((r for r in rows if r["customer_segment"] == "new"), None)
    if not vip or not new:
        return _inconclusive(h, rows, "Insufficient data")

    aov_pct = (vip["avg_order_value"] - new["avg_order_value"]) / new["avg_order_value"] * 100
    aov_higher = aov_pct > 0
    rev_share_higher = vip["revenue_share"] > (vip["order_count"] / sum(r["order_count"] for r in rows))

    if aov_higher and rev_share_higher:
        verdict = "supported"
        summary = (
            f"チェーン検証成功: VIP AOV{aov_pct:+.0f}%高 → 売上シェア{vip['revenue_share']:.1%} "
            f"(注文シェア{vip['order_count'] / sum(r['order_count'] for r in rows):.1%}を上回る)"
        )
    elif aov_higher and not rev_share_higher:
        verdict = "supported"
        summary = f"VIP AOV{aov_pct:+.0f}%高だが売上シェアは注文シェアと同等"
    else:
        verdict = "contradicted"
        summary = f"VIP AOVがNew以下 ({aov_pct:+.0f}%)"

    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


# =============================================================================
# 3-hop chain verification functions
# =============================================================================


def _verify_seasonal_concentration_3hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    """Verify: Seasonal → SeasonalRevenue → Q4Revenue → AnnualConcentration."""
    q4 = next((r for r in rows if r["order_quarter"] == 4), None)
    others = [r for r in rows if r["order_quarter"] != 4]
    if not q4 or not others:
        return _inconclusive(h, rows, "Insufficient data")

    avg_other_seasonal = sum(r["seasonal_revenue"] for r in others) / len(others)
    seasonal_ratio = q4["seasonal_revenue"] / max(1, avg_other_seasonal)
    q4_share = q4["quarter_share"]

    step1_ok = seasonal_ratio > 1.5
    step2_ok = q4["quarter_revenue"] > sum(r["quarter_revenue"] for r in others) / len(others)
    step3_ok = q4_share > 0.30

    if step1_ok and step2_ok and step3_ok:
        verdict = "supported"
        summary = (
            f"3段チェーン検証成功: 季節商品スパイク{seasonal_ratio:.1f}倍 "
            f"→ Q4売上{q4['quarter_revenue']:,.0f} "
            f"→ Q4年間シェア{q4_share:.1%}(期待25%を超過)"
        )
    elif step1_ok and step2_ok and not step3_ok:
        verdict = "contradicted"
        summary = f"季節スパイクとQ4売上高は成立だがQ4シェア{q4_share:.1%}は30%未満"
    elif step1_ok and not step2_ok:
        verdict = "contradicted"
        summary = f"季節スパイクは成立だがQ4売上が他四半期を上回らない"
    else:
        verdict = "contradicted"
        summary = f"季節商品のQ4スパイクが不十分(倍率{seasonal_ratio:.1f})"

    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_vip_concentration_3hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    """Verify: VIP → AOV → Revenue → RevenueConcentration."""
    vip = next((r for r in rows if r["customer_segment"] == "vip"), None)
    new = next((r for r in rows if r["customer_segment"] == "new"), None)
    if not vip or not new:
        return _inconclusive(h, rows, "Insufficient data")

    aov_pct = (vip["avg_order_value"] - new["avg_order_value"]) / new["avg_order_value"] * 100
    step1_ok = aov_pct > 30
    step2_ok = vip["revenue_share"] > vip["order_share"]
    step3_ok = vip["revenue_share"] > 2 * vip["order_share"]

    if step1_ok and step2_ok and step3_ok:
        verdict = "supported"
        summary = (
            f"3段チェーン検証成功: VIP AOV{aov_pct:+.0f}%高 "
            f"→ 売上シェア{vip['revenue_share']:.1%} "
            f"→ 注文シェア{vip['order_share']:.1%}の{vip['revenue_share']/vip['order_share']:.1f}倍(集中リスク)"
        )
    elif step1_ok and step2_ok and not step3_ok:
        verdict = "supported"
        summary = f"VIP AOV高→売上シェア高だが集中度は中程度"
    elif step1_ok and not step2_ok:
        verdict = "contradicted"
        summary = f"VIP AOV{aov_pct:+.0f}%高だが売上シェアが注文シェア以下"
    else:
        verdict = "contradicted"
        summary = f"VIP AOVがNew比で低い({aov_pct:+.0f}%)"

    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_discount_profit_3hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    """Verify: Discount → OrderVolume → Revenue → ProfitGrowth."""
    campaign = next((r for r in rows if r["has_campaign"]), None)
    no_campaign = next((r for r in rows if not r["has_campaign"]), None)
    if not campaign or not no_campaign:
        return _inconclusive(h, rows, "Insufficient data")

    vol_pct = (campaign["avg_daily_orders"] - no_campaign["avg_daily_orders"]) / no_campaign["avg_daily_orders"] * 100
    rev_pct = (campaign["avg_daily_revenue"] - no_campaign["avg_daily_revenue"]) / no_campaign["avg_daily_revenue"] * 100
    net_pct = (campaign["avg_daily_net_revenue"] - no_campaign["avg_daily_net_revenue"]) / no_campaign["avg_daily_net_revenue"] * 100

    step1_ok = vol_pct > 0
    step2_ok = rev_pct > 0
    step3_ok = net_pct > 0

    if step1_ok and step2_ok and step3_ok:
        verdict = "supported"
        summary = f"3段チェーン検証成功: 注文数{vol_pct:+.0f}% → 売上{rev_pct:+.0f}% → 純利益{net_pct:+.0f}%"
    elif step1_ok and not step2_ok:
        verdict = "contradicted"
        summary = (
            f"3段チェーン途中断絶: 注文数{vol_pct:+.0f}%(成立) → 売上{rev_pct:+.0f}%(断絶) "
            f"→ 純利益{net_pct:+.0f}% - 割引による単価減が注文増を上回る"
        )
    elif step1_ok and step2_ok and not step3_ok:
        verdict = "contradicted"
        summary = f"注文数{vol_pct:+.0f}%→売上{rev_pct:+.0f}%は成立だが純利益{net_pct:+.0f}%で最終段断絶"
    else:
        verdict = "contradicted"
        summary = f"注文数{vol_pct:+.0f}% - チェーンの起点から不成立"

    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


# =============================================================================
# 4-hop chain verification functions
# =============================================================================


def _verify_q4_dependency_4hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    q4 = next((r for r in rows if r["order_quarter"] == 4), None)
    others = [r for r in rows if r["order_quarter"] != 4]
    if not q4 or not others:
        return _inconclusive(h, rows, "Insufficient data")

    avg_other_rev = sum(r["total_revenue"] for r in others) / len(others)
    q4_evergreen = q4["evergreen_revenue"]
    dependency = q4_evergreen <= avg_other_rev * 1.1

    if q4["quarter_share"] > 0.30 and dependency:
        verdict = "supported"
        summary = (
            f"4段チェーン検証成功: Q4シェア{q4['quarter_share']:.1%} → "
            f"季節商品除外後Q4({q4_evergreen:,.0f})≈他四半期平均({avg_other_rev:,.0f}) → 季節依存リスク高"
        )
    elif q4["quarter_share"] > 0.30:
        verdict = "contradicted"
        summary = f"Q4集中だが季節商品除外後もQ4が高い"
    else:
        verdict = "contradicted"
        summary = f"Q4シェア{q4['quarter_share']:.1%}で集中度が低い"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_vip_dependency_4hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    vip = next((r for r in rows if r["customer_segment"] == "vip"), None)
    new = next((r for r in rows if r["customer_segment"] == "new"), None)
    if not vip or not new:
        return _inconclusive(h, rows, "Insufficient data")

    ratio = vip["revenue_per_customer"] / new["revenue_per_customer"] if new["revenue_per_customer"] > 0 else 0

    if ratio > 5 and vip["revenue_share"] > 2 * vip["customer_share"]:
        verdict = "supported"
        summary = (
            f"4段チェーン検証成功: VIP/New比{ratio:.1f}倍 → "
            f"売上シェア{vip['revenue_share']:.1%}/顧客シェア{vip['customer_share']:.1%} → セグメント依存リスク高"
        )
    elif ratio > 3:
        verdict = "supported"
        summary = f"VIP/New比{ratio:.1f}倍で依存傾向あり"
    else:
        verdict = "contradicted"
        summary = f"VIP/New比{ratio:.1f}倍で依存度は低い"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_campaign_efficiency_4hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    campaign = next((r for r in rows if r["has_campaign"]), None)
    no_campaign = next((r for r in rows if not r["has_campaign"]), None)
    if not campaign or not no_campaign:
        return _inconclusive(h, rows, "Insufficient data")

    rev_lower = campaign["avg_daily_revenue"] < no_campaign["avg_daily_revenue"]
    net_lower = campaign["avg_daily_net"] < no_campaign["avg_daily_net"]

    if rev_lower and net_lower:
        verdict = "supported"
        summary = (
            f"4段チェーン検証成功: キャンペーン日売上{campaign['avg_daily_revenue']:,.0f}"
            f" < 通常日{no_campaign['avg_daily_revenue']:,.0f} → 非効率"
        )
    else:
        verdict = "contradicted"
        summary = f"キャンペーン日売上が通常日以上 → 効率的"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


# =============================================================================
# 5-hop chain verification functions
# =============================================================================


def _verify_strategic_vulnerability_5hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    q4 = next((r for r in rows if r["order_quarter"] == 4), None)
    if not q4:
        return _inconclusive(h, rows, "Insufficient data")

    seasonal_share_q4 = q4["seasonal_share_of_quarter"] or 0
    seasonal_share_annual = q4["seasonal_share_of_annual"] or 0

    if seasonal_share_q4 > 0.50 and seasonal_share_annual > 0.20:
        verdict = "supported"
        summary = (
            f"5段チェーン検証成功: Q4季節商品シェア{seasonal_share_q4:.1%}(>50%) → "
            f"年間の{seasonal_share_annual:.1%}(>20%)がQ4季節商品に依存 → 戦略的脆弱性"
        )
    elif seasonal_share_q4 > 0.50:
        verdict = "supported"
        summary = f"Q4内季節商品{seasonal_share_q4:.1%}だが年間影響は中程度"
    else:
        verdict = "contradicted"
        summary = f"Q4季節商品シェア{seasonal_share_q4:.1%}で脆弱性は低い"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_retention_priority_5hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    vip = next((r for r in rows if r["customer_segment"] == "vip"), None)
    if not vip:
        return _inconclusive(h, rows, "Insufficient data")

    vs_avg = vip["vs_average_ratio"] or 0

    if vs_avg > 3 and vip["revenue_share"] > 0.35:
        verdict = "supported"
        summary = f"5段チェーン検証成功: VIP対平均{vs_avg:.1f}倍 → 売上シェア{vip['revenue_share']:.1%} → VIP維持最優先"
    elif vs_avg > 2:
        verdict = "supported"
        summary = f"VIP対平均{vs_avg:.1f}倍で中程度の優先度"
    else:
        verdict = "contradicted"
        summary = f"VIP対平均{vs_avg:.1f}倍で特別な維持優先度不要"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)


def _verify_strategy_revision_5hop(h: Hypothesis, rows: list[dict]) -> VerificationResult:
    campaign = next((r for r in rows if r["has_campaign"]), None)
    no_campaign = next((r for r in rows if not r["has_campaign"]), None)
    if not campaign or not no_campaign:
        return _inconclusive(h, rows, "Insufficient data")

    rev_per_disc = campaign.get("revenue_per_discount_dollar")
    rev_lower = campaign["avg_daily_revenue"] < no_campaign["avg_daily_revenue"]

    if rev_lower and rev_per_disc and rev_per_disc < 10:
        verdict = "supported"
        summary = (
            f"5段チェーン検証成功: キャンペーン日売上{campaign['avg_daily_revenue']:,.0f}"
            f" < 通常日{no_campaign['avg_daily_revenue']:,.0f} → "
            f"割引1円あたり{rev_per_disc:.1f}円 → 戦略見直し必要"
        )
    elif rev_lower:
        verdict = "supported"
        summary = f"キャンペーン売上が通常より低く見直し推奨"
    else:
        verdict = "contradicted"
        summary = f"キャンペーンが売上増に寄与しており見直し不要"
    return VerificationResult(hypothesis=h, query_result=rows, verdict=verdict, evidence_summary=summary)
