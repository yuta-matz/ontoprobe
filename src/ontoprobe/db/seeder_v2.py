"""Synthetic data generator v2: causal-inference-ready EC data.

Data generating process follows the ontology DAG structure:
  Campaign → OrderVolume (+12%) → Revenue
  Campaign → AOV (-5%) → Revenue
  Seasonal → OrderVolume (+60% in Q4) → Revenue
  Weekend → OrderVolume (+15%) → Revenue
  Payday → OrderVolume (+10%) → Revenue

Revenue = Orders × AOV (mediation structure preserved)

Hidden confounder (daily_potential) drives both campaign placement
and base order volume, creating selection bias.
"""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

from ontoprobe.config import SEED_DIR

SEED = 43
random.seed(SEED)

CAMPAIGNS_V2 = [
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

# === TRUE DGP PARAMETERS ===
# Each parameter maps to an ontology causal rule.

# Campaign → OrderVolume (ontology: "Discount increases order volume", expected 15-30%)
TRUE_CAMPAIGN_ORDER_BOOST = 0.12  # +12% (below expectation of 15-30%)

# Campaign → AOV (ontology: "Discount suppresses AOV", expected -10 to -25%)
TRUE_CAMPAIGN_AOV_REDUCTION = 0.05  # -5% (less than expected -10 to -25%)

# Net campaign effect on revenue: 1.12 × 0.95 = 1.064 → +6.4%
# (ontology: "Discount → DailyRevenue", expected +5 to +15%)

# Seasonal → OrderVolume (ontology: "Q4 has highest revenue", expected +30-50%)
TRUE_Q4_ORDER_BOOST = 0.60  # +60% (above expectation of 30-50%)

# Weekend → OrderVolume
TRUE_WEEKEND_ORDER_BOOST = 0.15  # +15%

# Payday → OrderVolume
TRUE_PAYDAY_ORDER_BOOST = 0.10  # +10%

# Base values
BASE_DAILY_ORDERS = 6.0
BASE_AOV = 10000  # JPY

# Selection bias: marketing places campaigns on high-potential days
SELECTION_BIAS_STRENGTH = 0.4


def _is_payday_week(d: date) -> bool:
    return abs(d.day - 25) <= 3


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _active_discount_campaign(order_date: date) -> int | None:
    for cid, _, ctype, start, end, _ in CAMPAIGNS_V2:
        if ctype == "discount" and date.fromisoformat(start) <= order_date <= date.fromisoformat(end):
            return cid
    return None


def _daily_potential(d: date) -> float:
    """Hidden daily sales potential (unobserved confounder)."""
    day_hash = hash((d.year, d.month, d.day, SEED)) % 1000 / 1000.0
    return math.sin(day_hash * math.pi * 2) * 0.3


def generate_daily_data() -> list[dict]:
    """Generate day-level data following the ontology DAG structure.

    Causal paths:
      Campaign → Orders (+12%) → Revenue
      Campaign → AOV (-5%) → Revenue
      Q4 → Orders (+60%) → Revenue
      Weekend → Orders (+15%) → Revenue
      Payday → Orders (+10%) → Revenue
      Hidden potential → Orders + Campaign placement (confounder)

    Revenue = Orders × AOV (structural equation)
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

        # === Step 1: Campaign assignment (endogenous) ===
        scheduled_campaign = _active_discount_campaign(d)
        if scheduled_campaign is not None:
            has_discount = True
            campaign_id = scheduled_campaign
        else:
            # Ad-hoc campaigns on high-potential days (selection bias)
            adhoc_prob = max(0, min(0.15, 0.05 + potential * SELECTION_BIAS_STRENGTH))
            if random.random() < adhoc_prob:
                has_discount = True
                campaign_id = -1
            else:
                has_discount = False
                campaign_id = None

        # === Step 2: Order volume (mediator 1) ===
        orders = BASE_DAILY_ORDERS
        # Seasonal effect on orders
        if quarter == 4:
            orders *= (1 + TRUE_Q4_ORDER_BOOST)
        elif quarter == 2:
            orders *= 1.08
        # Weekend effect on orders
        if weekend:
            orders *= (1 + TRUE_WEEKEND_ORDER_BOOST)
        # Payday effect on orders
        if payday:
            orders *= (1 + TRUE_PAYDAY_ORDER_BOOST)
        # Hidden potential → orders (confounder path)
        orders *= (1 + potential * 0.15)
        # Campaign → orders (TRUE CAUSAL EFFECT)
        campaign_order_effect = 0.0
        if has_discount:
            campaign_order_effect = TRUE_CAMPAIGN_ORDER_BOOST
            orders *= (1 + campaign_order_effect)
        # Noise
        orders *= (1 + random.gauss(0, 0.12))
        orders = max(1, round(orders))

        # Counterfactual orders (without campaign)
        cf_orders = orders / (1 + campaign_order_effect) if has_discount else orders

        # === Step 3: AOV (mediator 2) ===
        aov = BASE_AOV
        # Seasonal effect on AOV (Q4 higher-value products)
        if quarter == 4:
            aov *= 1.25
        # VIP mix variation (random daily fluctuation)
        aov *= (1 + random.gauss(0, 0.08))
        # Campaign → AOV (TRUE CAUSAL EFFECT: discount reduces AOV)
        campaign_aov_effect = 0.0
        if has_discount:
            campaign_aov_effect = -TRUE_CAMPAIGN_AOV_REDUCTION
            aov *= (1 + campaign_aov_effect)
        aov = max(3000, round(aov))

        # Counterfactual AOV
        cf_aov = aov / (1 + campaign_aov_effect) if has_discount else aov

        # === Step 4: Revenue = Orders × AOV (structural equation) ===
        revenue = int(orders * aov)
        cf_revenue = int(cf_orders * cf_aov)
        true_effect = revenue - cf_revenue

        rows.append({
            "date": d.isoformat(),
            "day_of_week": dow,
            "day_name": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][dow],
            "is_weekend": int(weekend),
            "is_payday_week": int(payday),
            "quarter": quarter,
            "month": month,
            "has_discount_campaign": int(has_discount),
            "campaign_id": campaign_id,
            "daily_orders": int(orders),
            "daily_aov": int(aov),
            "daily_revenue": revenue,
            # Hidden ground truth
            "_daily_potential": round(potential, 4),
            "_cf_orders": round(cf_orders),
            "_cf_aov": round(cf_aov),
            "_cf_revenue": cf_revenue,
            "_true_effect": true_effect,
            "_true_effect_pct": round(true_effect / cf_revenue * 100, 2) if cf_revenue > 0 else 0,
        })

    return rows


def save_daily_csv(rows: list[dict], out_dir: Path | None = None) -> Path:
    if out_dir is None:
        out_dir = SEED_DIR.parent / "causal"
    out_dir.mkdir(parents=True, exist_ok=True)

    obs_cols = [
        "date", "day_of_week", "day_name", "is_weekend", "is_payday_week",
        "quarter", "month", "has_discount_campaign", "campaign_id",
        "daily_orders", "daily_aov", "daily_revenue",
    ]
    obs_path = out_dir / "daily_observable.csv"
    with open(obs_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=obs_cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    full_path = out_dir / "daily_full_with_ground_truth.csv"
    with open(full_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    return obs_path


def print_summary(rows: list[dict]) -> None:
    campaign_days = [r for r in rows if r["has_discount_campaign"]]
    non_campaign = [r for r in rows if not r["has_discount_campaign"]]

    avg_orders_c = sum(r["daily_orders"] for r in campaign_days) / len(campaign_days)
    avg_orders_nc = sum(r["daily_orders"] for r in non_campaign) / len(non_campaign)
    avg_aov_c = sum(r["daily_aov"] for r in campaign_days) / len(campaign_days)
    avg_aov_nc = sum(r["daily_aov"] for r in non_campaign) / len(non_campaign)
    avg_rev_c = sum(r["daily_revenue"] for r in campaign_days) / len(campaign_days)
    avg_rev_nc = sum(r["daily_revenue"] for r in non_campaign) / len(non_campaign)

    true_effects = [r["_true_effect_pct"] for r in campaign_days]
    avg_true_pct = sum(true_effects) / len(true_effects)

    print(f"Total days: {len(rows)}")
    print(f"Campaign days: {len(campaign_days)} ({len(campaign_days)/len(rows)*100:.1f}%)")
    print()
    print(f"=== Naive estimates (confounded) ===")
    print(f"  Orders:  campaign {avg_orders_c:.1f} vs non {avg_orders_nc:.1f} → +{(avg_orders_c/avg_orders_nc-1)*100:.1f}%")
    print(f"  AOV:     campaign {avg_aov_c:,.0f} vs non {avg_aov_nc:,.0f} → {(avg_aov_c/avg_aov_nc-1)*100:+.1f}%")
    print(f"  Revenue: campaign {avg_rev_c:,.0f} vs non {avg_rev_nc:,.0f} → +{(avg_rev_c/avg_rev_nc-1)*100:.1f}%")
    print()
    print(f"=== True DGP parameters ===")
    print(f"  Campaign → Orders: +{TRUE_CAMPAIGN_ORDER_BOOST*100:.0f}% (ontology expects +15-30%)")
    print(f"  Campaign → AOV:    -{TRUE_CAMPAIGN_AOV_REDUCTION*100:.0f}% (ontology expects -10 to -25%)")
    print(f"  Net on revenue:    +{avg_true_pct:.1f}% (ontology expects +5-15%)")
    print(f"  Q4 → Orders:       +{TRUE_Q4_ORDER_BOOST*100:.0f}% (ontology expects +30-50%)")


if __name__ == "__main__":
    data = generate_daily_data()
    path = save_daily_csv(data)
    print(f"Saved to: {path}\n")
    print_summary(data)
