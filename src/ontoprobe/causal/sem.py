"""Structural Equation Modeling from ontology DAG.

Translates the ontology's causal structure into a system of linear equations:
  Eq1: Orders = β₁·Campaign + β₂·Q4 + β₃·Weekend + β₄·Payday + ε₁
  Eq2: AOV = γ₁·Campaign + γ₂·Q4 + ε₂
  Eq3: Revenue = δ₁·Orders + δ₂·AOV + ε₃  (structural: Revenue ≈ Orders × AOV)

Each coefficient maps to an ontology causal rule with an expected magnitude.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ontoprobe.causal.partial_id import load_daily_data


@dataclass
class PathEstimate:
    """Estimated effect for one causal path."""
    path: str           # e.g. "Campaign → Orders"
    coefficient: float  # Estimated effect (percentage)
    std_err: float
    ontology_expected: str  # e.g. "+15-30%"
    comparison: str     # "期待以下" / "期待通り" / "期待以上"


@dataclass
class SEMResult:
    """Full SEM estimation result."""
    paths: list[PathEstimate]
    naive_revenue_effect: float
    sem_net_revenue_effect: float
    true_revenue_effect: float | None  # Only available with ground truth


def _ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Simple OLS returning coefficients and standard errors."""
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    residuals = y - X @ beta
    n, k = X.shape
    sigma2 = (residuals @ residuals) / (n - k)
    se = np.sqrt(np.diag(sigma2 * XtX_inv))
    return beta, se


def estimate_sem(df: pd.DataFrame | None = None) -> SEMResult:
    """Estimate the structural equation model from daily data.

    Structure (from ontology DAG):
      Campaign → Orders (expected +15-30%)
      Campaign → AOV (expected -10 to -25%)
      Q4 → Orders (expected +30-50% on revenue, via orders)
      Weekend → Orders
      Payday → Orders
      Revenue = Orders × AOV
    """
    if df is None:
        df = load_daily_data(observable_only=True)

    df = df.copy()

    # Normalize for percentage interpretation
    mean_orders = df["daily_orders"].mean()
    mean_aov = df["daily_aov"].mean()
    mean_revenue = df["daily_revenue"].mean()

    # === Eq1: Orders = f(Campaign, Q4, Weekend, Payday) ===
    y1 = df["daily_orders"].values.astype(float)
    X1 = np.column_stack([
        np.ones(len(df)),
        df["has_discount_campaign"].values.astype(float),
        (df["quarter"] == 4).values.astype(float),
        df["is_weekend"].values.astype(float),
        df["is_payday_week"].values.astype(float),
    ])
    beta1, se1 = _ols(y1, X1)
    # beta1: [intercept, campaign, Q4, weekend, payday]

    campaign_order_effect_pct = (beta1[1] / beta1[0]) * 100
    q4_order_effect_pct = (beta1[2] / beta1[0]) * 100
    weekend_order_effect_pct = (beta1[3] / beta1[0]) * 100
    payday_order_effect_pct = (beta1[4] / beta1[0]) * 100

    # === Eq2: AOV = f(Campaign, Q4) ===
    y2 = df["daily_aov"].values.astype(float)
    X2 = np.column_stack([
        np.ones(len(df)),
        df["has_discount_campaign"].values.astype(float),
        (df["quarter"] == 4).values.astype(float),
    ])
    beta2, se2 = _ols(y2, X2)
    campaign_aov_effect_pct = (beta2[1] / beta2[0]) * 100
    q4_aov_effect_pct = (beta2[2] / beta2[0]) * 100

    # === Net revenue effect of campaign ===
    # Revenue = Orders × AOV
    # Δ Revenue ≈ (1 + order_effect) × (1 + aov_effect) - 1
    net_campaign_pct = (1 + campaign_order_effect_pct / 100) * (1 + campaign_aov_effect_pct / 100) - 1
    net_campaign_pct *= 100

    # === Naive estimate for comparison ===
    treated = df[df["has_discount_campaign"] == 1]
    control = df[df["has_discount_campaign"] == 0]
    naive_pct = (treated["daily_revenue"].mean() / control["daily_revenue"].mean() - 1) * 100

    # === Build path estimates ===
    def _compare(estimated: float, exp_low: float, exp_high: float) -> str:
        if estimated < exp_low:
            return "期待以下"
        elif estimated > exp_high:
            return "期待以上"
        else:
            return "期待通り"

    paths = [
        PathEstimate(
            path="Campaign → Orders（注文数）",
            coefficient=round(campaign_order_effect_pct, 1),
            std_err=round(se1[1] / beta1[0] * 100, 1),
            ontology_expected="+15〜30%",
            comparison=_compare(campaign_order_effect_pct, 15, 30),
        ),
        PathEstimate(
            path="Campaign → AOV（客単価）",
            coefficient=round(campaign_aov_effect_pct, 1),
            std_err=round(se2[1] / beta2[0] * 100, 1),
            ontology_expected="-10〜-25%",
            comparison=_compare(campaign_aov_effect_pct, -25, -10),
        ),
        PathEstimate(
            path="Campaign → Revenue（売上ネット）",
            coefficient=round(net_campaign_pct, 1),
            std_err=0,  # Derived
            ontology_expected="+5〜15%",
            comparison=_compare(net_campaign_pct, 5, 15),
        ),
        PathEstimate(
            path="Q4 → Orders（季節効果）",
            coefficient=round(q4_order_effect_pct, 1),
            std_err=round(se1[2] / beta1[0] * 100, 1),
            ontology_expected="+30〜50%（売上ベース）",
            comparison=_compare(q4_order_effect_pct, 30, 50),
        ),
        PathEstimate(
            path="Q4 → AOV（季節商品ミックス）",
            coefficient=round(q4_aov_effect_pct, 1),
            std_err=round(se2[2] / beta2[0] * 100, 1),
            ontology_expected="—",
            comparison="—",
        ),
        PathEstimate(
            path="Weekend → Orders",
            coefficient=round(weekend_order_effect_pct, 1),
            std_err=round(se1[3] / beta1[0] * 100, 1),
            ontology_expected="—",
            comparison="—",
        ),
    ]

    # True effect (if available)
    true_pct = None
    try:
        df_full = load_daily_data(observable_only=False)
        campaign_rows = df_full[df_full["has_discount_campaign"] == 1]
        true_pct = campaign_rows["_true_effect_pct"].mean()
    except Exception:
        pass

    return SEMResult(
        paths=paths,
        naive_revenue_effect=round(naive_pct, 1),
        sem_net_revenue_effect=round(net_campaign_pct, 1),
        true_revenue_effect=round(true_pct, 1) if true_pct is not None else None,
    )


if __name__ == "__main__":
    result = estimate_sem()
    print("=== SEM: ontology DAG → 構造方程式 ===\n")
    for p in result.paths:
        print(f"  {p.path}")
        print(f"    SEM推定: {p.coefficient:+.1f}% (±{p.std_err:.1f})")
        print(f"    期待値:  {p.ontology_expected}")
        print(f"    判定:    {p.comparison}")
        print()
    print(f"ナイーブ推定（売上）: +{result.naive_revenue_effect:.1f}%")
    print(f"SEM推定（売上ネット）: {result.sem_net_revenue_effect:+.1f}%")
    if result.true_revenue_effect is not None:
        print(f"真の因果効果:         +{result.true_revenue_effect:.1f}%")
