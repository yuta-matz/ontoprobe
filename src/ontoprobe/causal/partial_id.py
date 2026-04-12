"""Partial identification of causal effects from observational data.

Implements Manski bounds with progressive assumption strengthening:
  Step 1: No assumptions (outcome bounds only)
  Step 2: MTR (Monotone Treatment Response) — from ontology direction
  Step 3: Covariate conditioning — observed confounders
  Step 4: MTS (Monotone Treatment Selection) — marketing places campaigns strategically
  Step 5: Compare bounds to ontology expectedMagnitude
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Bounds:
    """Identified bounds on the ATE (as percentage effect on outcome)."""
    lower: float  # Lower bound (percentage)
    upper: float  # Upper bound (percentage)
    assumption: str  # What assumptions were used
    step: int

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper

    def __repr__(self) -> str:
        return f"[{self.lower:+.1f}%, {self.upper:+.1f}%] ({self.assumption})"


@dataclass
class BoundsComparison:
    """Comparison of bounds against ontology expected magnitude."""
    bounds: Bounds
    expected_lower: float  # Ontology expectation lower (%)
    expected_upper: float  # Ontology expectation upper (%)
    conclusion: str


def load_daily_data(observable_only: bool = True) -> pd.DataFrame:
    """Load the v2 daily causal data."""
    from pathlib import Path
    data_dir = Path(__file__).resolve().parents[3] / "data" / "causal"
    if observable_only:
        return pd.read_csv(data_dir / "daily_observable.csv")
    return pd.read_csv(data_dir / "daily_full_with_ground_truth.csv")


def step1_no_assumptions(df: pd.DataFrame, outcome: str = "daily_revenue") -> Bounds:
    """Manski bounds with no assumptions.

    ATE ∈ [E[Y|T=1] - Y_max, E[Y|T=1] - Y_min]
    where Y_max/Y_min are the outcome bounds.
    """
    treated = df[df["has_discount_campaign"] == True]  # noqa: E712
    control = df[df["has_discount_campaign"] == False]  # noqa: E712

    ey1 = treated[outcome].mean()
    ey0 = control[outcome].mean()
    y_min = df[outcome].min()
    y_max = df[outcome].max()

    # Bounds on E[Y(1)] - E[Y(0)]
    # Worst case: treated would have had Y_max without treatment, control would have had Y_min with treatment
    lower_abs = ey1 - y_max  # If all control units would have Y_max under treatment
    upper_abs = ey1 - y_min  # If all control units would have Y_min under treatment

    # Convert to percentage effect relative to control mean
    lower_pct = (lower_abs / ey0) * 100
    upper_pct = (upper_abs / ey0) * 100

    return Bounds(
        lower=round(lower_pct, 1),
        upper=round(upper_pct, 1),
        assumption="仮定なし（結果変数の値域のみ）",
        step=1,
    )


def step2_mtr(df: pd.DataFrame, outcome: str = "daily_revenue") -> Bounds:
    """Add Monotone Treatment Response: Y(1) >= Y(0) for all units.

    From ontology: direction = "increase" → campaign doesn't decrease revenue.
    This sets the lower bound to 0.
    """
    treated = df[df["has_discount_campaign"] == True]  # noqa: E712
    control = df[df["has_discount_campaign"] == False]  # noqa: E712

    ey1 = treated[outcome].mean()
    ey0 = control[outcome].mean()
    y_max = df[outcome].max()

    upper_abs = ey1 - ey0 + (y_max - ey0) * 0.5  # Tighten with MTR
    upper_pct = (upper_abs / ey0) * 100

    return Bounds(
        lower=0.0,
        upper=round(min(upper_pct, 100.0), 1),
        assumption="+ 単調処置応答 MTR（ontology: direction = increase）",
        step=2,
    )


def step3_conditional(df: pd.DataFrame, outcome: str = "daily_revenue",
                       covariates: list[str] | None = None) -> Bounds:
    """Condition on observed covariates to tighten MTR bounds.

    Within each stratum (quarter × weekend × payday), compute:
    - Lower: 0 (from MTR)
    - Upper: stratum Y_max - stratum E[Y|T=0] (MTR upper, no MTS yet)
    Then take weighted average across strata.
    """
    if covariates is None:
        covariates = ["quarter", "is_weekend", "is_payday_week"]

    df = df.copy()
    df["_strata"] = df[covariates].astype(str).agg("_".join, axis=1)

    weighted_upper = 0.0
    total_weight = 0.0

    for stratum, group in df.groupby("_strata"):
        treated = group[group["has_discount_campaign"] == True]  # noqa: E712
        control = group[group["has_discount_campaign"] == False]  # noqa: E712

        if len(treated) < 2 or len(control) < 2:
            continue

        ey0 = control[outcome].mean()
        y_max_stratum = group[outcome].max()

        # MTR within stratum: ATE <= Y_max_stratum - E[Y|T=0]
        upper_abs = y_max_stratum - ey0
        upper_pct = (upper_abs / ey0) * 100

        weight = len(group)
        weighted_upper += upper_pct * weight
        total_weight += weight

    if total_weight == 0:
        return step2_mtr(df, outcome)

    avg_upper = weighted_upper / total_weight

    return Bounds(
        lower=0.0,
        upper=round(min(avg_upper, 100.0), 1),
        assumption="+ 共変量条件付き MTR（曜日・季節・給料日週で層別化）",
        step=3,
    )


def step4_mts(df: pd.DataFrame, outcome: str = "daily_revenue",
               covariates: list[str] | None = None) -> Bounds:
    """Add Monotone Treatment Selection: E[Y(0)|T=1] >= E[Y(0)|T=0].

    Marketing places campaigns on high-potential days → positive selection.
    Under MTR + MTS:
      - Lower: 0 (from MTR)
      - Upper: within-stratum naive estimate E[Y|T=1] - E[Y|T=0]
        (MTS guarantees naive is upper bound on true effect)
    This is strictly tighter than Step 3 because naive < Y_max - E[Y|T=0].
    """
    if covariates is None:
        covariates = ["quarter", "is_weekend", "is_payday_week"]

    df = df.copy()
    df["_strata"] = df[covariates].astype(str).agg("_".join, axis=1)

    weighted_upper = 0.0
    total_weight = 0.0

    for stratum, group in df.groupby("_strata"):
        treated = group[group["has_discount_campaign"] == True]  # noqa: E712
        control = group[group["has_discount_campaign"] == False]  # noqa: E712

        if len(treated) < 2 or len(control) < 2:
            continue

        ey1 = treated[outcome].mean()
        ey0 = control[outcome].mean()

        # Under MTS: naive = E[Y|T=1] - E[Y|T=0] is UPPER bound on ATE
        naive_pct = (ey1 / ey0 - 1) * 100
        # Clamp: MTS upper can't be negative under MTR
        upper_pct = max(0.0, naive_pct)

        weight = len(group)
        weighted_upper += upper_pct * weight
        total_weight += weight

    if total_weight == 0:
        return step3_conditional(df, outcome, covariates)

    upper = weighted_upper / total_weight

    return Bounds(
        lower=0.0,
        upper=round(upper, 1),
        assumption="+ 単調処置選択 MTS（マーケは売上ポテンシャルが高い日にキャンペーン配置）",
        step=4,
    )


def step5_compare_expectation(bounds: Bounds,
                                expected_lower: float = 5.0,
                                expected_upper: float = 15.0) -> BoundsComparison:
    """Compare partial identification bounds with ontology expected magnitude."""
    if bounds.upper < expected_lower:
        conclusion = (
            f"bounds 上限（{bounds.upper:+.1f}%）が期待下限（{expected_lower:+.1f}%）を下回る。\n"
            f"最も楽観的な仮定でもキャンペーン効果は期待以下。"
        )
    elif bounds.lower > expected_upper:
        conclusion = (
            f"bounds 下限（{bounds.lower:+.1f}%）が期待上限（{expected_upper:+.1f}%）を上回る。\n"
            f"最も悲観的な仮定でもキャンペーン効果は期待以上。"
        )
    elif bounds.lower >= expected_lower and bounds.upper <= expected_upper:
        conclusion = (
            f"bounds [{bounds.lower:+.1f}%, {bounds.upper:+.1f}%] が"
            f"期待値範囲 [{expected_lower:+.1f}%, {expected_upper:+.1f}%] に完全に含まれる。\n"
            f"期待通りの効果。"
        )
    else:
        conclusion = (
            f"bounds [{bounds.lower:+.1f}%, {bounds.upper:+.1f}%] と"
            f"期待値範囲 [{expected_lower:+.1f}%, {expected_upper:+.1f}%] が部分的に重なる。\n"
            f"判定保留 — bounds をさらに狭める追加仮定が必要。"
        )

    return BoundsComparison(
        bounds=bounds,
        expected_lower=expected_lower,
        expected_upper=expected_upper,
        conclusion=conclusion,
    )


def run_all_steps(df: pd.DataFrame | None = None,
                   outcome: str = "daily_revenue",
                   expected_lower: float = 5.0,
                   expected_upper: float = 15.0) -> list[Bounds | BoundsComparison]:
    """Run all partial identification steps and return results."""
    if df is None:
        df = load_daily_data(observable_only=True)

    results = []

    b1 = step1_no_assumptions(df, outcome)
    results.append(b1)

    b2 = step2_mtr(df, outcome)
    results.append(b2)

    b3 = step3_conditional(df, outcome)
    results.append(b3)

    b4 = step4_mts(df, outcome)
    results.append(b4)

    comparison = step5_compare_expectation(b4, expected_lower, expected_upper)
    results.append(comparison)

    return results


if __name__ == "__main__":
    df = load_daily_data(observable_only=True)
    df_full = load_daily_data(observable_only=False)

    print("=== Partial Identification: Discount Campaign → Daily Revenue ===\n")

    results = run_all_steps(df)
    for r in results:
        if isinstance(r, BoundsComparison):
            print(f"\nStep 5: 期待値との比較")
            print(f"  Bounds:  {r.bounds}")
            print(f"  期待値:  [{r.expected_lower:+.1f}%, {r.expected_upper:+.1f}%]")
            print(f"  結論:    {r.conclusion}")
        else:
            print(f"Step {r.step}: {r}")

    # Validate against ground truth
    treated = df_full[df_full["has_discount_campaign"] == True]  # noqa: E712
    true_effects = treated["_true_effect"] / treated["_counterfactual_revenue"] * 100
    print(f"\n=== Ground Truth ===")
    print(f"True ATE: +{true_effects.mean():.1f}%")
    print(f"Bounds contain true value? {results[3].contains(true_effects.mean())}")
