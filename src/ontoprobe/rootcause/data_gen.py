"""Multi-round synthetic data with per-round shock injection.

Extends seeder_v2's DGP so that each 30-day 'round' can be generated with
its own set of levers. Overriding exactly one lever injects a known upstream
shock whose propagation can be traced backward via the ontology.

Levers:
    campaign_frequency     — P(day has a discount campaign)
    campaign_order_boost   — Campaign → order volume uplift
    campaign_aov_reduction — Campaign → AOV reduction (discount effect on price mix)
    discount_percent       — Discount depth when a campaign is active
    vip_share              — Share of orders that come from VIP customers
    vip_aov_multiplier     — VIP orders get base_aov * multiplier
    seasonal_share         — Share of orders that are seasonal products
    base_daily_orders / base_aov / weekend_* / payday_* / q4_* — shape controls

Scenarios (Phase 2):
    S1 discount_withdrawn  — campaign_frequency 0.25 → 0.0  (primary lever: DiscountCampaign)
    S2 vip_churn           — vip_share 0.25 → 0.05          (primary lever: VIPCustomer)
    S3 seasonal_collapse   — seasonal_share 0.30 → 0.00     (primary lever: SeasonalProduct)
"""

from __future__ import annotations

import csv
import json
import random
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

from ontoprobe.config import DATA_DIR

SEED = 43
ROUND_DAYS = 30
ROOTCAUSE_DIR = DATA_DIR / "rootcause"


@dataclass
class Levers:
    campaign_frequency: float = 0.25
    campaign_order_boost: float = 0.12
    campaign_aov_reduction: float = 0.05
    discount_percent: float = 20.0
    vip_share: float = 0.25
    vip_aov_multiplier: float = 1.6
    seasonal_share: float = 0.30
    base_daily_orders: float = 8.0
    base_aov: float = 10_000
    weekend_order_boost: float = 0.15
    payday_order_boost: float = 0.10
    q4_order_boost: float = 0.60
    noise_orders: float = 0.12
    # Phase 10: flip downstream relationships to CONTRADICT the LLM prior.
    # When True, this round operates in a 'prior-contradicting' world where:
    #   - VIP customers get bulk discounts → VIP AOV multiplier < 1
    #   - Discount campaigns signal clearance → campaign reduces order volume
    #   - Q4 supply constraints → Q4 reduces orders instead of boosting them
    #   - Seasonal revenue is inversely proportional to seasonal items
    inverted: bool = False


@dataclass
class Round:
    round_id: str
    label: str
    start_date: date
    levers: Levers
    shocked_lever: str | None = None
    shocked_from: float | None = None
    shocked_to: float | None = None
    shocked_concept: str | None = None
    expected_downstream: list[str] = field(default_factory=list)
    seed: int = SEED


@dataclass
class Scenario:
    scenario_id: str
    description: str
    baseline: Round
    anomaly: Round
    seed: int = SEED


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _is_payday_week(d: date) -> bool:
    return abs(d.day - 25) <= 3


def _generate_round_rows(r: Round, rng: random.Random) -> list[dict]:
    rows: list[dict] = []
    lv = r.levers

    # Phase 10: apply prior-contradicting inversions when requested.
    # The sign flips below make the synthetic world run opposite to
    # typical e-commerce intuition, so that an LLM agent acting on its
    # training-data prior would arrive at wrong conclusions. The inverted
    # ontology must mirror these flips for the agent to succeed.
    if lv.inverted:
        vip_aov_multiplier = 0.5  # VIPs get bulk discounts → lower AOV
        campaign_order_boost_effective = -0.15  # campaigns suppress orders
        q4_order_boost_effective = -0.25  # Q4 supply constraints
    else:
        vip_aov_multiplier = lv.vip_aov_multiplier
        campaign_order_boost_effective = lv.campaign_order_boost
        q4_order_boost_effective = lv.q4_order_boost

    for day_offset in range(ROUND_DAYS):
        d = r.start_date + timedelta(days=day_offset)
        weekend = _is_weekend(d)
        payday = _is_payday_week(d)
        quarter = (d.month - 1) // 3 + 1

        has_discount = rng.random() < lv.campaign_frequency
        discount_pct = lv.discount_percent if has_discount else 0.0

        orders = lv.base_daily_orders
        if weekend:
            orders *= 1 + lv.weekend_order_boost
        if payday:
            orders *= 1 + lv.payday_order_boost
        if quarter == 4:
            orders *= 1 + q4_order_boost_effective
        if has_discount:
            orders *= 1 + campaign_order_boost_effective
        orders *= 1 + rng.gauss(0, lv.noise_orders)
        orders = max(1, round(orders))

        # Split orders into VIP vs non-VIP (binomial split via per-order draws)
        vip_orders = sum(1 for _ in range(orders) if rng.random() < lv.vip_share)
        non_vip_orders = orders - vip_orders

        # Seasonal item share — also a per-order draw (independent of VIP)
        seasonal_orders = sum(
            1 for _ in range(orders) if rng.random() < lv.seasonal_share
        )

        base_aov = lv.base_aov
        if quarter == 4:
            base_aov *= 1.25
        aov_noise = 1 + rng.gauss(0, 0.08)
        non_vip_aov = max(3000, round(base_aov * aov_noise))
        vip_aov = max(3000, round(base_aov * vip_aov_multiplier * aov_noise))

        if has_discount:
            non_vip_aov = round(non_vip_aov * (1 - lv.campaign_aov_reduction))
            vip_aov = round(vip_aov * (1 - lv.campaign_aov_reduction * 0.5))

        vip_gross = vip_orders * vip_aov
        non_vip_gross = non_vip_orders * non_vip_aov
        gross_revenue = vip_gross + non_vip_gross
        discount_amount = (
            int(gross_revenue * discount_pct / 100) if has_discount else 0
        )
        net_revenue = gross_revenue - discount_amount

        avg_aov = gross_revenue / max(1, orders)
        if lv.inverted:
            # Inverted: non-seasonal items drive 'seasonal revenue'.
            # Semantically nonsense but mechanically flips the direction
            # so that higher seasonal_share LOWERS seasonal_revenue.
            non_seasonal_orders = orders - seasonal_orders
            seasonal_revenue = int(non_seasonal_orders * avg_aov * 1.1)
        else:
            seasonal_revenue = int(seasonal_orders * avg_aov * 1.1)

        rows.append(
            {
                "round_id": r.round_id,
                "date": d.isoformat(),
                "quarter": quarter,
                "is_weekend": int(weekend),
                "is_payday_week": int(payday),
                "has_discount_campaign": int(has_discount),
                "discount_percent": discount_pct,
                "daily_orders": orders,
                "daily_vip_orders": vip_orders,
                "daily_seasonal_orders": seasonal_orders,
                "daily_gross_revenue": gross_revenue,
                "daily_vip_gross_revenue": vip_gross,
                "daily_discount_amount": discount_amount,
                "daily_revenue": net_revenue,
                "daily_seasonal_revenue": seasonal_revenue,
            }
        )
    return rows


def _make_scenario(
    scenario_id: str,
    description: str,
    anomaly_label: str,
    shocked_lever: str,
    shocked_from: float,
    shocked_to: float,
    shocked_concept: str,
    expected_downstream: list[str],
    seed: int = SEED,
    inverted: bool = False,
) -> Scenario:
    baseline = Round(
        round_id=f"{scenario_id}_R1",
        label="Baseline",
        start_date=date(2025, 5, 1),
        levers=replace(Levers(), inverted=inverted),
        seed=seed,
    )
    anomaly_kwargs: dict = {shocked_lever: shocked_to, "inverted": inverted}
    anomaly = Round(
        round_id=f"{scenario_id}_R2",
        label=anomaly_label,
        start_date=date(2025, 6, 1),
        levers=replace(Levers(), **anomaly_kwargs),
        shocked_lever=shocked_lever,
        shocked_from=shocked_from,
        shocked_to=shocked_to,
        shocked_concept=shocked_concept,
        expected_downstream=expected_downstream,
        seed=seed + 1,
    )
    return Scenario(
        scenario_id=scenario_id,
        description=description,
        baseline=baseline,
        anomaly=anomaly,
        seed=seed,
    )


def build_scenarios() -> list[Scenario]:
    """15 scenarios: 3 concepts × 5 magnitudes each.

    Each concept is shocked via a single lever at five intensities (strong
    down / partial down / mild down / mild up / strong up) so the ablation
    can test whether the ontology helps across direction and magnitude.
    """
    # (suffix, lever_value, label_suffix)
    discount_variants = [
        ("off", 0.0, "fully withdrawn"),
        ("partial_off", 0.10, "partially withdrawn"),
        ("mild_off", 0.15, "mildly reduced"),
        ("mild_up", 0.40, "mildly extended"),
        ("surge", 0.50, "doubled"),
    ]
    vip_variants = [
        ("strong_down", 0.05, "severely churned"),
        ("partial_down", 0.12, "partially churned"),
        ("mild_down", 0.18, "slightly churned"),
        ("mild_up", 0.35, "mildly boosted"),
        ("surge", 0.45, "strongly boosted"),
    ]
    seasonal_variants = [
        ("off", 0.02, "supply collapsed"),
        ("partial_off", 0.12, "partially disrupted"),
        ("mild_off", 0.20, "mildly reduced"),
        ("mild_up", 0.45, "mildly expanded"),
        ("surge", 0.55, "strongly expanded"),
    ]

    scenarios: list[Scenario] = []
    default_levers = Levers()

    for i, (suffix, to_val, label_suffix) in enumerate(discount_variants, start=1):
        scenarios.append(
            _make_scenario(
                scenario_id=f"D{i}",
                description=f"Discount campaigns {label_suffix}",
                anomaly_label=f"Discount {label_suffix}",
                shocked_lever="campaign_frequency",
                shocked_from=default_levers.campaign_frequency,
                shocked_to=to_val,
                shocked_concept="Discount Campaign",
                expected_downstream=["Discount", "Order Volume", "Revenue"],
            )
        )

    for i, (suffix, to_val, label_suffix) in enumerate(vip_variants, start=1):
        scenarios.append(
            _make_scenario(
                scenario_id=f"V{i}",
                description=f"VIP customer traffic {label_suffix}",
                anomaly_label=f"VIP {label_suffix}",
                shocked_lever="vip_share",
                shocked_from=default_levers.vip_share,
                shocked_to=to_val,
                shocked_concept="VIP Customer",
                expected_downstream=["Average Order Value", "Revenue"],
            )
        )

    for i, (suffix, to_val, label_suffix) in enumerate(seasonal_variants, start=1):
        scenarios.append(
            _make_scenario(
                scenario_id=f"S{i}",
                description=f"Seasonal products {label_suffix}",
                anomaly_label=f"Seasonal {label_suffix}",
                shocked_lever="seasonal_share",
                shocked_from=default_levers.seasonal_share,
                shocked_to=to_val,
                shocked_concept="Seasonal Product",
                expected_downstream=["Seasonal Revenue", "Revenue"],
            )
        )

    return scenarios


def build_discount_focused_scenarios() -> list[Scenario]:
    """20 scenarios all with DiscountCampaign as ground truth.

    4 magnitudes × 5 seeds, mirroring the VIP-focused builder. Shocks
    campaign_frequency away from the 0.25 baseline at strong-down /
    partial-down / mild-up / strong-up intensities.
    """
    magnitudes = [0.05, 0.10, 0.40, 0.45]
    seeds = [101, 211, 317, 431, 547]
    scenarios: list[Scenario] = []
    default_levers = Levers()
    for mag in magnitudes:
        for seed in seeds:
            mag_tag = f"{int(mag * 100):02d}"
            scenarios.append(
                _make_scenario(
                    scenario_id=f"DF_{mag_tag}_{seed}",
                    description=(
                        f"Campaign frequency shocked to {mag} (seed {seed}) — "
                        "class-typed discount cause"
                    ),
                    anomaly_label=f"Campaign freq → {mag}",
                    shocked_lever="campaign_frequency",
                    shocked_from=default_levers.campaign_frequency,
                    shocked_to=mag,
                    shocked_concept="Discount Campaign",
                    expected_downstream=["Discount", "Order Volume", "Revenue"],
                    seed=seed,
                )
            )
    return scenarios


def build_seasonal_focused_scenarios() -> list[Scenario]:
    """20 scenarios all with SeasonalProduct as ground truth.

    4 magnitudes × 5 seeds, mirroring the VIP-focused builder. Shocks
    seasonal_share away from the 0.30 baseline.
    """
    magnitudes = [0.05, 0.10, 0.50, 0.55]
    seeds = [101, 211, 317, 431, 547]
    scenarios: list[Scenario] = []
    default_levers = Levers()
    for mag in magnitudes:
        for seed in seeds:
            mag_tag = f"{int(mag * 100):02d}"
            scenarios.append(
                _make_scenario(
                    scenario_id=f"SF_{mag_tag}_{seed}",
                    description=(
                        f"Seasonal share shocked to {mag} (seed {seed}) — "
                        "class-typed seasonal cause"
                    ),
                    anomaly_label=f"Seasonal share → {mag}",
                    shocked_lever="seasonal_share",
                    shocked_from=default_levers.seasonal_share,
                    shocked_to=mag,
                    shocked_concept="Seasonal Product",
                    expected_downstream=["Seasonal Revenue", "Revenue"],
                    seed=seed,
                )
            )
    return scenarios


def build_inverted_vip_scenarios() -> list[Scenario]:
    """Phase 10: prior-contradicting VIP scenarios.

    Identical shock structure to build_vip_focused_scenarios, but each
    scenario runs in the inverted DGP (vip_aov_multiplier = 0.5 so VIPs
    have LOWER AOV). The LLM prior expects 'more VIPs → higher revenue'
    but the reality is the opposite.
    """
    magnitudes = [0.10, 0.15, 0.35, 0.40]
    seeds = [101, 211, 317, 431, 547]
    scenarios: list[Scenario] = []
    default_levers = Levers()
    for mag in magnitudes:
        for seed in seeds:
            mag_tag = f"{int(mag * 100):02d}"
            scenarios.append(
                _make_scenario(
                    scenario_id=f"INV_VF_{mag_tag}_{seed}",
                    description=(
                        f"[INVERTED] VIP share shocked to {mag} (seed {seed}) — "
                        "VIPs have LOWER AOV in this world"
                    ),
                    anomaly_label=f"[INV] VIP share → {mag}",
                    shocked_lever="vip_share",
                    shocked_from=default_levers.vip_share,
                    shocked_to=mag,
                    shocked_concept="VIP Customer",
                    expected_downstream=["Average Order Value", "Revenue"],
                    seed=seed,
                    inverted=True,
                )
            )
    return scenarios


def build_inverted_discount_scenarios() -> list[Scenario]:
    """Phase 10: prior-contradicting discount scenarios.

    campaign_order_boost = -0.15 so running a campaign REDUCES order
    volume (clearance-signal interpretation). LLM prior expects
    'campaigns → more orders → more revenue'; reality is the opposite.
    """
    magnitudes = [0.05, 0.10, 0.40, 0.45]
    seeds = [101, 211, 317, 431, 547]
    scenarios: list[Scenario] = []
    default_levers = Levers()
    for mag in magnitudes:
        for seed in seeds:
            mag_tag = f"{int(mag * 100):02d}"
            scenarios.append(
                _make_scenario(
                    scenario_id=f"INV_DF_{mag_tag}_{seed}",
                    description=(
                        f"[INVERTED] Campaign freq shocked to {mag} (seed {seed}) — "
                        "discounts REDUCE volume in this world"
                    ),
                    anomaly_label=f"[INV] Campaign freq → {mag}",
                    shocked_lever="campaign_frequency",
                    shocked_from=default_levers.campaign_frequency,
                    shocked_to=mag,
                    shocked_concept="Discount Campaign",
                    expected_downstream=["Order Volume", "Revenue"],
                    seed=seed,
                    inverted=True,
                )
            )
    return scenarios


def build_inverted_seasonal_scenarios() -> list[Scenario]:
    """Phase 10: prior-contradicting seasonal scenarios.

    Seasonal revenue is computed from NON-seasonal items in the inverted
    DGP, so increasing seasonal_share LOWERS seasonal_revenue. LLM prior
    expects 'more seasonal items → more seasonal revenue'; reality is
    the opposite.
    """
    magnitudes = [0.05, 0.10, 0.50, 0.55]
    seeds = [101, 211, 317, 431, 547]
    scenarios: list[Scenario] = []
    default_levers = Levers()
    for mag in magnitudes:
        for seed in seeds:
            mag_tag = f"{int(mag * 100):02d}"
            scenarios.append(
                _make_scenario(
                    scenario_id=f"INV_SF_{mag_tag}_{seed}",
                    description=(
                        f"[INVERTED] Seasonal share shocked to {mag} (seed {seed}) — "
                        "seasonal items REDUCE seasonal revenue in this world"
                    ),
                    anomaly_label=f"[INV] Seasonal share → {mag}",
                    shocked_lever="seasonal_share",
                    shocked_from=default_levers.seasonal_share,
                    shocked_to=mag,
                    shocked_concept="Seasonal Product",
                    expected_downstream=["Seasonal Revenue", "Revenue"],
                    seed=seed,
                    inverted=True,
                )
            )
    return scenarios


def build_vip_focused_scenarios() -> list[Scenario]:
    """20 scenarios all with VIPCustomer as ground truth.

    4 magnitudes × 5 RNG seeds. Magnitudes are picked to straddle the
    difficulty sweet spot where the VIP → Revenue signal is detectable
    but distractor metrics move enough to mislead a no-ontology agent.
    Each seed yields a different distractor pattern (random VIP/seasonal
    draws, AOV noise) so the A/M0 vs B/M4 comparison is not dominated by
    a single idiosyncratic round.
    """
    magnitudes = [0.10, 0.15, 0.35, 0.40]
    seeds = [101, 211, 317, 431, 547]
    scenarios: list[Scenario] = []
    default_levers = Levers()
    for mag in magnitudes:
        for seed in seeds:
            mag_tag = f"{int(mag * 100):02d}"
            scenarios.append(
                _make_scenario(
                    scenario_id=f"VF_{mag_tag}_{seed}",
                    description=(
                        f"VIP share shocked to {mag} (seed {seed}) — "
                        "class-typed cause, mid-range signal"
                    ),
                    anomaly_label=f"VIP share → {mag}",
                    shocked_lever="vip_share",
                    shocked_from=default_levers.vip_share,
                    shocked_to=mag,
                    shocked_concept="VIP Customer",
                    expected_downstream=["Average Order Value", "Revenue"],
                    seed=seed,
                )
            )
    return scenarios


def generate_scenario_rows(scenario: Scenario) -> list[dict]:
    rng_baseline = random.Random(scenario.baseline.seed)
    rng_anomaly = random.Random(scenario.anomaly.seed)
    return _generate_round_rows(scenario.baseline, rng_baseline) + _generate_round_rows(
        scenario.anomaly, rng_anomaly
    )


def save_scenarios(
    scenarios: list[Scenario], out_dir: Path = ROOTCAUSE_DIR
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    for s in scenarios:
        all_rows.extend(generate_scenario_rows(s))

    csv_path = out_dir / "rounds.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

    meta_path = out_dir / "ground_truth.json"
    with open(meta_path, "w") as f:
        json.dump(
            [
                {
                    "scenario_id": s.scenario_id,
                    "description": s.description,
                    "baseline_round": s.baseline.round_id,
                    "anomaly_round": s.anomaly.round_id,
                    "shocked_lever": s.anomaly.shocked_lever,
                    "shocked_from": s.anomaly.shocked_from,
                    "shocked_to": s.anomaly.shocked_to,
                    "shocked_concept": s.anomaly.shocked_concept,
                    "expected_downstream": s.anomaly.expected_downstream,
                }
                for s in scenarios
            ],
            f,
            indent=2,
        )
    return csv_path


def build_phase1_scenario() -> tuple[list[dict], list[Round]]:
    """Backwards-compatible shim for scripts/run_rootcause.py (first scenario only)."""
    scenarios = build_scenarios()
    s1 = scenarios[0]
    s1.baseline.round_id = "R1"
    s1.anomaly.round_id = "R2"
    rows = generate_scenario_rows(s1)
    return rows, [s1.baseline, s1.anomaly]


def save_rounds(
    rows: list[dict],
    rounds: list[Round],
    out_dir: Path = ROOTCAUSE_DIR,
) -> Path:
    """Backwards-compatible shim used by scripts/run_rootcause.py."""
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "rounds.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    meta_path = out_dir / "ground_truth.json"
    with open(meta_path, "w") as f:
        json.dump(
            [
                {
                    "round_id": r.round_id,
                    "label": r.label,
                    "start_date": r.start_date.isoformat(),
                    "levers": asdict(r.levers),
                    "shocked_lever": r.shocked_lever,
                    "shocked_from": r.shocked_from,
                    "shocked_to": r.shocked_to,
                    "shocked_concept": r.shocked_concept,
                    "expected_downstream": r.expected_downstream,
                }
                for r in rounds
            ],
            f,
            indent=2,
        )
    return csv_path


if __name__ == "__main__":
    scenarios = build_scenarios()
    path = save_scenarios(scenarios)
    print(f"Saved scenarios to {path}")
    for s in scenarios:
        print(
            f"  {s.scenario_id} ({s.description}): "
            f"{s.anomaly.shocked_lever} "
            f"{s.anomaly.shocked_from} → {s.anomaly.shocked_to}"
        )
