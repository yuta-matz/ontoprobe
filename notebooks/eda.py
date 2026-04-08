import marimo

__generated_with = "0.13.0"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(
        r"""
        # OntoProbe PoC データ EDA

        ECサイトのPoCデータ（2025年1月〜12月）の探索的データ分析。
        DuckDB上の合成データを対象とする。

        - 顧客: 200名（New / Returning / VIP）
        - 商品: 12品目（季節商品4 / 通年商品8）
        - 注文: 2,318件
        - キャンペーン: 5件（割引3 / 送料無料2）
        """
    )
    return


@app.cell
def _():
    import marimo as mo
    import duckdb
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    from pathlib import Path

    DB_PATH = Path(__file__).parent.parent / "data" / "ontoprobe.duckdb"
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    return DB_PATH, Path, conn, duckdb, go, make_subplots, mo, px


@app.cell
def _(conn, mo):
    mo.md("## 1. データ概要")
    return


@app.cell
def _(conn, mo):
    tables = conn.execute("""
        SELECT table_name,
               (SELECT COUNT(*) FROM information_schema.columns c
                WHERE c.table_name = t.table_name AND c.table_schema = 'main') as columns
        FROM (
            SELECT DISTINCT table_name
            FROM information_schema.tables
            WHERE table_schema = 'main'
        ) t
        ORDER BY table_name
    """).fetchdf()
    counts = []
    for tn in tables["table_name"]:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tn}").fetchone()[0]
        counts.append(cnt)
    tables["rows"] = counts
    mo.ui.table(tables)
    return counts, tables


@app.cell
def _(conn, mo):
    mo.md("## 2. 顧客分析")
    return


@app.cell
def _(conn, mo, px):
    seg = conn.execute("""
        SELECT customer_segment, COUNT(*) AS count
        FROM customers
        GROUP BY customer_segment
    """).fetchdf()
    fig_seg = px.pie(seg, values="count", names="customer_segment",
                     title="顧客セグメント構成",
                     color_discrete_sequence=px.colors.qualitative.Set2)
    mo.ui.plotly(fig_seg)
    return (fig_seg, seg)


@app.cell
def _(conn, mo, px):
    region = conn.execute("""
        SELECT region, customer_segment, COUNT(*) AS count
        FROM customers
        GROUP BY region, customer_segment
        ORDER BY region, customer_segment
    """).fetchdf()
    fig_region = px.bar(region, x="region", y="count", color="customer_segment",
                        title="地域×セグメント別の顧客数",
                        barmode="group",
                        color_discrete_sequence=px.colors.qualitative.Set2)
    mo.ui.plotly(fig_region)
    return (fig_region, region)


@app.cell
def _(conn, mo, px):
    cust_stats = conn.execute("""
        SELECT customer_segment,
               AVG(total_orders) AS avg_orders,
               AVG(lifetime_revenue) AS avg_ltv,
               AVG(avg_order_value) AS avg_aov
        FROM dim_customers
        GROUP BY customer_segment
        ORDER BY avg_ltv DESC
    """).fetchdf()
    fig_ltv = px.bar(cust_stats, x="customer_segment", y="avg_ltv",
                     title="セグメント別 平均LTV",
                     text_auto=".0f",
                     color="customer_segment",
                     color_discrete_sequence=px.colors.qualitative.Set2)
    fig_ltv.update_layout(showlegend=False)
    mo.ui.plotly(fig_ltv)
    return (cust_stats, fig_ltv)


@app.cell
def _(conn, mo, px):
    aov_dist = conn.execute("""
        SELECT customer_segment, avg_order_value
        FROM dim_customers
        WHERE avg_order_value > 0
    """).fetchdf()
    fig_aov_box = px.box(aov_dist, x="customer_segment", y="avg_order_value",
                         title="セグメント別 AOV分布",
                         color="customer_segment",
                         color_discrete_sequence=px.colors.qualitative.Set2)
    fig_aov_box.update_layout(showlegend=False)
    mo.ui.plotly(fig_aov_box)
    return (aov_dist, fig_aov_box)


@app.cell
def _(conn, mo):
    mo.md("## 3. 売上トレンド")
    return


@app.cell
def _(conn, go, make_subplots, mo):
    monthly = conn.execute("""
        SELECT order_month,
               SUM(total_amount) AS revenue,
               COUNT(*) AS orders,
               AVG(total_amount) AS aov
        FROM fct_orders
        GROUP BY order_month
        ORDER BY order_month
    """).fetchdf()

    fig_trend = make_subplots(rows=2, cols=1,
                              shared_xaxes=True,
                              subplot_titles=("月次売上", "月次注文数・AOV"),
                              vertical_spacing=0.12)

    fig_trend.add_trace(
        go.Bar(x=monthly["order_month"], y=monthly["revenue"],
               name="売上", marker_color="#2ecc71"),
        row=1, col=1
    )
    fig_trend.add_trace(
        go.Bar(x=monthly["order_month"], y=monthly["orders"],
               name="注文数", marker_color="#3498db"),
        row=2, col=1
    )
    fig_trend.add_trace(
        go.Scatter(x=monthly["order_month"], y=monthly["aov"],
                   name="AOV", mode="lines+markers",
                   marker_color="#e74c3c", yaxis="y4"),
        row=2, col=1
    )
    fig_trend.update_layout(
        height=500, title_text="月次売上トレンド",
        yaxis2=dict(title="注文数"),
    )
    fig_trend.update_xaxes(title_text="月", row=2, col=1,
                           tickmode="linear", dtick=1)
    fig_trend.update_yaxes(title_text="売上", row=1, col=1)
    mo.ui.plotly(fig_trend)
    return (fig_trend, monthly)


@app.cell
def _(conn, mo, px):
    quarterly = conn.execute("""
        SELECT order_quarter,
               customer_segment,
               SUM(total_amount) AS revenue
        FROM fct_orders
        GROUP BY order_quarter, customer_segment
        ORDER BY order_quarter, customer_segment
    """).fetchdf()
    fig_q = px.bar(quarterly, x="order_quarter", y="revenue",
                   color="customer_segment",
                   title="四半期×セグメント別 売上",
                   barmode="stack",
                   color_discrete_sequence=px.colors.qualitative.Set2)
    fig_q.update_xaxes(title="四半期", tickmode="linear", dtick=1)
    mo.ui.plotly(fig_q)
    return (fig_q, quarterly)


@app.cell
def _(conn, mo):
    mo.md("## 4. 季節商品分析")
    return


@app.cell
def _(conn, mo, px):
    seasonal_monthly = conn.execute("""
        SELECT order_month,
               SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) AS seasonal_revenue,
               SUM(CASE WHEN NOT is_seasonal THEN line_total ELSE 0 END) AS evergreen_revenue
        FROM fct_order_items
        GROUP BY order_month
        ORDER BY order_month
    """).fetchdf()

    fig_seasonal = px.bar(
        seasonal_monthly.melt(id_vars="order_month",
                              value_vars=["seasonal_revenue", "evergreen_revenue"],
                              var_name="type", value_name="revenue"),
        x="order_month", y="revenue", color="type",
        title="月次 季節商品 vs 通年商品 売上",
        barmode="stack",
        color_discrete_map={
            "seasonal_revenue": "#e74c3c",
            "evergreen_revenue": "#3498db"
        },
        labels={"type": "商品タイプ", "revenue": "売上", "order_month": "月"}
    )
    fig_seasonal.update_xaxes(tickmode="linear", dtick=1)
    mo.ui.plotly(fig_seasonal)
    return (fig_seasonal, seasonal_monthly)


@app.cell
def _(conn, mo, px):
    product_sales = conn.execute("""
        SELECT p.product_name, p.is_seasonal, p.category_name,
               SUM(oi.line_total) AS total_revenue,
               SUM(oi.quantity) AS total_qty
        FROM fct_order_items oi
        JOIN dim_products p USING (product_id)
        GROUP BY p.product_name, p.is_seasonal, p.category_name
        ORDER BY total_revenue DESC
    """).fetchdf()
    fig_prod = px.bar(product_sales, x="product_name", y="total_revenue",
                      color="is_seasonal",
                      title="商品別 売上ランキング",
                      color_discrete_map={True: "#e74c3c", False: "#3498db"},
                      labels={"is_seasonal": "季節商品", "total_revenue": "売上"})
    fig_prod.update_layout(xaxis_tickangle=-45)
    mo.ui.plotly(fig_prod)
    return (fig_prod, product_sales)


@app.cell
def _(conn, mo, px):
    seasonal_q = conn.execute("""
        SELECT order_quarter,
               p.product_name,
               SUM(oi.line_total) AS revenue
        FROM fct_order_items oi
        JOIN dim_products p USING (product_id)
        WHERE p.is_seasonal = true
        GROUP BY order_quarter, p.product_name
        ORDER BY order_quarter, revenue DESC
    """).fetchdf()
    fig_sq = px.bar(seasonal_q, x="order_quarter", y="revenue",
                    color="product_name",
                    title="季節商品の四半期別売上",
                    barmode="group",
                    color_discrete_sequence=px.colors.qualitative.Vivid)
    fig_sq.update_xaxes(title="四半期", tickmode="linear", dtick=1)
    mo.ui.plotly(fig_sq)
    return (fig_sq, seasonal_q)


@app.cell
def _(conn, mo):
    mo.md("## 5. キャンペーン分析")
    return


@app.cell
def _(conn, mo):
    campaigns = conn.execute("""
        SELECT campaign_name, campaign_type, discount_percent,
               start_date, end_date, duration_days
        FROM dim_campaigns
        ORDER BY start_date
    """).fetchdf()
    mo.ui.table(campaigns)
    return (campaigns,)


@app.cell
def _(conn, go, make_subplots, mo):
    daily = conn.execute("""
        SELECT o.order_date,
               COUNT(*) AS orders,
               SUM(o.total_amount) AS revenue,
               COALESCE(c.campaign_name, '') AS campaign
        FROM fct_orders o
        LEFT JOIN dim_campaigns c USING (campaign_id)
        GROUP BY o.order_date, campaign
        ORDER BY o.order_date
    """).fetchdf()

    fig_daily = make_subplots(rows=2, cols=1,
                              shared_xaxes=True,
                              subplot_titles=("日次売上", "日次注文数"),
                              vertical_spacing=0.1)

    # Non-campaign days
    no_camp = daily[daily["campaign"] == ""]
    camp = daily[daily["campaign"] != ""]

    fig_daily.add_trace(
        go.Scatter(x=no_camp["order_date"], y=no_camp["revenue"],
                   mode="lines", name="通常", line=dict(color="#bdc3c7", width=1)),
        row=1, col=1
    )
    fig_daily.add_trace(
        go.Scatter(x=no_camp["order_date"], y=no_camp["orders"],
                   mode="lines", name="通常", line=dict(color="#bdc3c7", width=1),
                   showlegend=False),
        row=2, col=1
    )

    colors = {"Summer Sale": "#e74c3c", "Free Ship Week": "#2ecc71",
              "Black Friday": "#9b59b6", "Year End Sale": "#f39c12",
              "Spring Campaign": "#1abc9c"}
    for cname in camp["campaign"].unique():
        c_data = camp[camp["campaign"] == cname]
        color = colors.get(cname, "#3498db")
        fig_daily.add_trace(
            go.Scatter(x=c_data["order_date"], y=c_data["revenue"],
                       mode="markers", name=cname,
                       marker=dict(color=color, size=6)),
            row=1, col=1
        )
        fig_daily.add_trace(
            go.Scatter(x=c_data["order_date"], y=c_data["orders"],
                       mode="markers", name=cname,
                       marker=dict(color=color, size=6), showlegend=False),
            row=2, col=1
        )

    fig_daily.update_layout(height=500, title_text="日次推移とキャンペーン")
    mo.ui.plotly(fig_daily)
    return (camp, colors, daily, fig_daily, no_camp)


@app.cell
def _(conn, mo, px):
    camp_effect = conn.execute("""
        SELECT
            COALESCE(c.campaign_name, 'No Campaign') AS campaign,
            COALESCE(c.campaign_type, 'none') AS type,
            COALESCE(c.discount_percent, 0) AS discount_pct,
            COUNT(*) AS orders,
            AVG(o.total_amount) AS avg_aov,
            SUM(o.total_amount) AS total_revenue,
            SUM(o.discount_amount) AS total_discount
        FROM fct_orders o
        LEFT JOIN dim_campaigns c USING (campaign_id)
        GROUP BY campaign, type, discount_pct
        ORDER BY discount_pct
    """).fetchdf()
    fig_ce = px.scatter(camp_effect, x="orders", y="avg_aov",
                        size="total_revenue", color="campaign",
                        title="キャンペーン別 注文数×AOV（バブルサイズ=売上）",
                        hover_data=["discount_pct", "total_discount"],
                        color_discrete_sequence=px.colors.qualitative.Bold)
    mo.ui.plotly(fig_ce)
    return (camp_effect, fig_ce)


@app.cell
def _(conn, mo):
    mo.md("## 6. 地域分析")
    return


@app.cell
def _(conn, mo, px):
    region_q = conn.execute("""
        SELECT region, order_quarter,
               SUM(total_amount) AS revenue,
               COUNT(*) AS orders
        FROM fct_orders
        GROUP BY region, order_quarter
        ORDER BY region, order_quarter
    """).fetchdf()
    fig_rq = px.bar(region_q, x="order_quarter", y="revenue",
                    color="region", barmode="group",
                    title="四半期×地域別 売上",
                    color_discrete_sequence=px.colors.qualitative.Pastel)
    fig_rq.update_xaxes(title="四半期", tickmode="linear", dtick=1)
    mo.ui.plotly(fig_rq)
    return (fig_rq, region_q)


@app.cell
def _(conn, mo, px):
    region_seg = conn.execute("""
        SELECT region, customer_segment,
               SUM(total_amount) AS revenue,
               AVG(total_amount) AS aov
        FROM fct_orders
        GROUP BY region, customer_segment
        ORDER BY region, customer_segment
    """).fetchdf()
    fig_rs = px.bar(region_seg, x="region", y="revenue",
                    color="customer_segment",
                    title="地域×セグメント別 売上",
                    barmode="stack",
                    color_discrete_sequence=px.colors.qualitative.Set2)
    mo.ui.plotly(fig_rs)
    return (fig_rs, region_seg)


@app.cell
def _(conn, mo):
    mo.md("## 7. 基本統計量")
    return


@app.cell
def _(conn, mo):
    stats = conn.execute("""
        SELECT
            COUNT(*) AS total_orders,
            SUM(total_amount) AS total_revenue,
            AVG(total_amount) AS avg_order_value,
            MEDIAN(total_amount) AS median_order_value,
            MIN(total_amount) AS min_order_value,
            MAX(total_amount) AS max_order_value,
            STDDEV(total_amount) AS std_order_value,
            SUM(discount_amount) AS total_discounts,
            AVG(CASE WHEN discount_amount > 0 THEN discount_amount END) AS avg_discount_when_applied,
            SUM(CASE WHEN has_campaign THEN 1 ELSE 0 END) AS campaign_orders,
            ROUND(SUM(CASE WHEN has_campaign THEN 1 ELSE 0 END)::FLOAT / COUNT(*) * 100, 1) AS campaign_order_pct
        FROM fct_orders
    """).fetchdf().T.reset_index()
    stats.columns = ["指標", "値"]
    mo.ui.table(stats)
    return (stats,)


@app.cell
def _(conn, mo, px):
    order_dist = conn.execute("""
        SELECT total_amount FROM fct_orders
    """).fetchdf()
    fig_hist = px.histogram(order_dist, x="total_amount", nbins=50,
                            title="注文額分布",
                            labels={"total_amount": "注文額"},
                            color_discrete_sequence=["#3498db"])
    fig_hist.update_layout(showlegend=False)
    mo.ui.plotly(fig_hist)
    return (fig_hist, order_dist)


@app.cell
def _(conn, mo, px):
    items_per_order = conn.execute("""
        SELECT o.order_id, o.customer_segment,
               COUNT(oi.order_item_id) AS item_count,
               SUM(oi.quantity) AS total_qty
        FROM fct_orders o
        JOIN fct_order_items oi USING (order_id)
        GROUP BY o.order_id, o.customer_segment
    """).fetchdf()
    fig_items = px.box(items_per_order, x="customer_segment", y="total_qty",
                       title="セグメント別 1注文あたり購入数量",
                       color="customer_segment",
                       color_discrete_sequence=px.colors.qualitative.Set2)
    fig_items.update_layout(showlegend=False)
    mo.ui.plotly(fig_items)
    return (fig_items, items_per_order)


@app.cell
def _(conn, mo):
    mo.md(
        r"""
        ## 8. データの特徴まとめ

        このEDAから確認できる主な特徴:

        1. **Q4売上急増**: 10-12月の売上がQ1-Q3の約2倍。季節商品の需要集中が主因
        2. **VIPの圧倒的な購買力**: VIPは全顧客の15%だが売上の約48%を占める。AOVはNewの7倍
        3. **季節商品の偏り**: Q4の季節商品売上がQ1-Q3平均の15倍。冬物・ギフトに集中
        4. **キャンペーン効果の差**: 割引キャンペーンは注文数をやや増加させるが、送料無料は効果なし
        5. **地域差は小さい**: 5地域間の売上差は限定的。セグメント構成の影響が大きい
        """
    )
    return


@app.cell
def _(conn):
    conn.close()
    return


if __name__ == "__main__":
    app.run()
