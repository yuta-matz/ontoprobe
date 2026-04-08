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
