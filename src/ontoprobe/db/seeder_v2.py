"""Synthetic data generator v2: causal-inference-ready EC data.

Extends v1 seeder with:
- Campaigns spread across all quarters (breaks season-campaign confound)
- Observable confounders: day_of_week, is_weekend, is_payday_week
- Unobservable confounder: daily sales potential (hidden, drives campaign placement)
- Known true causal effect of discount campaigns on daily revenue (+8%)

The true DGP is documented so partial identification bounds can be validated
against ground truth.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

from ontoprobe.config import SEED_DIR
from ontoprobe.db.connection import get_connection

SEED = 43  # Different from v1 (42) to avoid confusion
random.seed(SEED)

REGIONS = ["tokyo", "osaka", "fukuoka", "sapporo", "nagoya"]
SEGMENTS = ["new", "returning", "vip"]

PRODUCTS = [
    # (id, name, category_id, price, is_seasonal)
    (1, "Wireless Earbuds", 1, 4980, False),
    (2, "USB-C Cable", 1, 1280, False),
    (3, "Smartphone Case", 1, 1980, False),
    (4, "T-Shirt Basic", 2, 2480, False),
    (5, "Sneakers", 2, 8980, False),
    (6, "Winter Coat", 5, 15980, True),
    (7, "Knit Scarf", 5, 3480, True),
    (8, "Organic Coffee", 3, 1680, False),
    (9, "Green Tea Set", 3, 2980, False),
    (10, "Desk Lamp", 4, 4480, False),
    (11, "Christmas Gift Box", 6, 5980, True),
    (12, "New Year Hamper", 6, 8980, True),
]

# Campaigns spread across all quarters to break seasonal confounding
CAMPAIGNS_V2 = [
    # (id, name, type, start, end, discount_percent)
    (1, "New Year Kickoff", "discount", "2025-01-15", "2025-01-25", 15),
    (2, "Valentine Promo", "free_shipping", "2025-02-10", "2025-02-16", 0),
    (3, "Spring Discount", "discount", "2025-04-20", "2025-04-30", 20),
    (4, "Early Summer Ship", "free_shipping", "2025-06-01", "2025-06-07", 0),
    (5, "Summer Sale", "discount", "2025-07-10", "2025-07-20", 20),
    (6, "Back to School", "free_shipping", "2025-08-15", "2025-08-22", 0),
    (7, "Autumn Discount", "discount", "2025-10-15", "2025-10-25", 15),
    (8, "Black Friday", "discount", "2025-11-25", "2025-11-30", 30),
    (9, "Year End Sale", "discount", "2025-12-20", "2025-12-31", 25),
]

START_DATE = date(2025, 1, 1)
END_DATE = date(2025, 12, 31)

# === TRUE DATA GENERATING PROCESS (DGP) PARAMETERS ===
# These are the ground truth for validating partial identification bounds.

TRUE_CAMPAIGN_EFFECT_ON_REVENUE = 0.08  # +8% true causal effect on daily revenue
# This is BELOW the ontology expectation of 5-15%, making it an interesting case
# where bounds + expectation comparison yields actionable insight.

SEASONAL_Q4_BOOST = 0.6  # Q4 base revenue is 60% higher
WEEKEND_EFFECT = 0.15  # Weekends have 15% higher revenue
PAYDAY_EFFECT = 0.10  # Payday week has 10% higher revenue

# Unobserved confounder: marketing team places campaigns on "good potential" days
# This creates upward bias in naive estimates
SELECTION_BIAS_STRENGTH = 0.4  # How much daily potential influences campaign placement


def _is_payday_week(d: date) -> bool:
    """25th of month ± 3 days."""
    return abs(d.day - 25) <= 3


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _active_discount_campaign(order_date: date) -> int | None:
    """Return campaign_id if a DISCOUNT campaign is active on this date."""
    for cid, _, ctype, start, end, _ in CAMPAIGNS_V2:
        if ctype == "discount" and date.fromisoformat(start) <= order_date <= date.fromisoformat(end):
            return cid
    return None


def _any_active_campaign(order_date: date) -> int | None:
    """Return campaign_id if ANY campaign is active."""
    for cid, _, _, start, end, _ in CAMPAIGNS_V2:
        if date.fromisoformat(start) <= order_date <= date.fromisoformat(end):
            return cid
    return None


def _daily_potential(d: date) -> float:
    """Hidden daily sales potential (unobserved confounder).

    This represents factors the marketing team can sense but aren't in the data:
    weather outlook, competitor activity, social media buzz, etc.
    """
    # Deterministic component from date (reproducible)
    day_hash = hash((d.year, d.month, d.day, SEED)) % 1000 / 1000.0
    # Smooth it with neighboring days for realism
    potential = math.sin(day_hash * math.pi * 2) * 0.3
    return potential


def generate_daily_data() -> list[dict]:
    """Generate day-level data with causal structure for partial identification.

    Returns one row per day with:
    - Observable: date, day_of_week, is_weekend, is_payday_week, quarter,
                  has_discount_campaign, campaign_id, daily_revenue, daily_orders
    - Hidden (for validation only): daily_potential, true_campaign_effect,
                  counterfactual_revenue
    """
    rows = []

    for day_offset in range((END_DATE - START_DATE).days + 1):
        d = START_DATE + timedelta(days=day_offset)
        month = d.month
        quarter = (month - 1) // 3 + 1
        dow = d.weekday()
        weekend = _is_weekend(d)
        payday = _is_payday_week(d)
        potential = _daily_potential(d)

        # --- Base revenue (no campaign) ---
        base = 50000  # Base daily revenue in JPY
        # Seasonal effect
        if quarter == 4:
            base *= (1 + SEASONAL_Q4_BOOST)
        elif quarter == 2:
            base *= 1.1  # Slight Q2 bump
        # Weekend effect
        if weekend:
            base *= (1 + WEEKEND_EFFECT)
        # Payday effect
        if payday:
            base *= (1 + PAYDAY_EFFECT)
        # Hidden potential (unobserved confounder)
        base *= (1 + potential * 0.2)
        # Daily noise
        base *= (1 + random.gauss(0, 0.15))

        # --- Campaign assignment (endogenous — depends on potential) ---
        scheduled_campaign = _active_discount_campaign(d)

        if scheduled_campaign is not None:
            has_discount = True
            campaign_id = scheduled_campaign
        else:
            # Marketing team sometimes adds ad-hoc campaigns on high-potential days
            # This is the SELECTION BIAS mechanism
            adhoc_prob = max(0, min(0.15, 0.05 + potential * SELECTION_BIAS_STRENGTH))
            if random.random() < adhoc_prob:
                has_discount = True
                campaign_id = -1  # Ad-hoc (not in campaign table)
            else:
                has_discount = False
                campaign_id = _any_active_campaign(d)  # might be free_shipping

        # --- True causal effect of discount campaign ---
        counterfactual_revenue = base  # What revenue would be WITHOUT campaign
        if has_discount:
            true_effect = base * TRUE_CAMPAIGN_EFFECT_ON_REVENUE
            actual_revenue = base + true_effect
        else:
            true_effect = 0
            actual_revenue = base

        # Compute order count from revenue (rough: revenue / avg_order_value)
        avg_order_value = 11000 if quarter == 4 else 8500
        daily_orders = max(1, int(actual_revenue / avg_order_value + random.gauss(0, 1)))
        actual_revenue = int(actual_revenue)
        counterfactual_revenue = int(counterfactual_revenue)

        rows.append({
            "date": d.isoformat(),
            "day_of_week": dow,
            "day_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dow],
            "is_weekend": weekend,
            "is_payday_week": payday,
            "quarter": quarter,
            "month": month,
            "has_discount_campaign": has_discount,
            "campaign_id": campaign_id if campaign_id and campaign_id > 0 else None,
            "daily_revenue": actual_revenue,
            "daily_orders": daily_orders,
            # Hidden ground truth (not available to analyst)
            "_daily_potential": round(potential, 4),
            "_true_effect": int(true_effect),
            "_counterfactual_revenue": counterfactual_revenue,
        })

    return rows


def save_daily_csv(rows: list[dict], out_dir: Path | None = None) -> Path:
    """Save daily data to CSV (observable columns only + hidden for validation)."""
    if out_dir is None:
        out_dir = SEED_DIR.parent / "causal"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Observable data (what the analyst sees)
    obs_path = out_dir / "daily_observable.csv"
    obs_cols = [
        "date", "day_of_week", "day_name", "is_weekend", "is_payday_week",
        "quarter", "month", "has_discount_campaign", "campaign_id",
        "daily_revenue", "daily_orders",
    ]
    with open(obs_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=obs_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    # Full data with hidden columns (for validation only)
    full_path = out_dir / "daily_full_with_ground_truth.csv"
    with open(full_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    return obs_path


def print_summary(rows: list[dict]) -> None:
    """Print summary statistics for validation."""
    campaign_days = [r for r in rows if r["has_discount_campaign"]]
    non_campaign_days = [r for r in rows if not r["has_discount_campaign"]]

    avg_rev_c = sum(r["daily_revenue"] for r in campaign_days) / len(campaign_days)
    avg_rev_nc = sum(r["daily_revenue"] for r in non_campaign_days) / len(non_campaign_days)
    naive_effect = (avg_rev_c / avg_rev_nc - 1) * 100

    true_effects = [r["_true_effect"] for r in campaign_days]
    avg_true = sum(true_effects) / len(true_effects)
    true_pct = avg_true / (avg_rev_c - avg_true) * 100

    print(f"Total days: {len(rows)}")
    print(f"Campaign days: {len(campaign_days)} ({len(campaign_days)/len(rows)*100:.1f}%)")
    print(f"Non-campaign days: {len(non_campaign_days)}")
    print()
    print(f"Avg daily revenue (campaign):     {avg_rev_c:,.0f}")
    print(f"Avg daily revenue (non-campaign): {avg_rev_nc:,.0f}")
    print(f"Naive estimate:                   +{naive_effect:.1f}%")
    print(f"True causal effect:               +{true_pct:.1f}%")
    print(f"Selection bias:                   +{naive_effect - true_pct:.1f}pp")
    print()
    print(f"DGP parameters:")
    print(f"  TRUE_CAMPAIGN_EFFECT = {TRUE_CAMPAIGN_EFFECT_ON_REVENUE*100:.0f}%")
    print(f"  SELECTION_BIAS_STRENGTH = {SELECTION_BIAS_STRENGTH}")


if __name__ == "__main__":
    data = generate_daily_data()
    path = save_daily_csv(data)
    print(f"Saved to: {path}")
    print()
    print_summary(data)
