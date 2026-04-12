"""Confirmatory mini-study analysis.

Pre-registered protocol: reports/confirmatory_protocol.md (commit c76a2a8).
Runs Wilcoxon, effect size, Cohen's kappa, bootstrap CI — all analyses
fixed in §9 of the protocol before data collection.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path

import marimo as mo

__generated_with__ = "confirmatory-1.0"
app = mo.App()


@app.cell
def _header():
    mo.md(
        """
        # Confirmatory Mini-Study Analysis

        **Pre-registered** per `reports/confirmatory_protocol.md` (git commit c76a2a8).
        Analysis plan is fixed; any deviation below is labeled *post-hoc*.
        """
    )
    return


@app.cell
def _load():
    data_dir = Path(__file__).resolve().parents[1] / "data" / "confirmatory"
    trials = {}
    for p in sorted(data_dir.glob("trial_*.json")):
        if p.name == "trial_plan.json":
            continue
        d = json.loads(p.read_text())
        trials[d["trial_uuid"]] = d

    scores = defaultdict(dict)
    for p in sorted((data_dir / "scores").glob("score_*.json")):
        d = json.loads(p.read_text())
        scores[d["trial_uuid"]][d["scorer_id"]] = d

    return trials, scores


@app.cell
def _per_cell(trials, scores):
    cell_q = defaultdict(list)
    cell_a = defaultdict(list)
    for uuid, t in trials.items():
        sa = scores[uuid]["scorer_a"]
        sb = scores[uuid]["scorer_b"]
        q_mean = (sa["q_quant"] + sb["q_quant"]) / 2
        a_mean = (sa["q_aware"] + sb["q_aware"]) / 2
        cell_q[(t["hid"], t["level"])].append(q_mean)
        cell_a[(t["hid"], t["level"])].append(a_mean)

    rows_q = []
    for hid in ("H1", "H2", "H3", "H4"):
        rows_q.append(
            {
                "hypothesis": hid,
                "L0 mean": statistics.mean(cell_q[(hid, 0)]),
                "L3 mean": statistics.mean(cell_q[(hid, 3)]),
                "gap (L3-L0)": statistics.mean(cell_q[(hid, 3)])
                - statistics.mean(cell_q[(hid, 0)]),
            }
        )
    mo.md("## Q_quant: quantitative deviation detection (per cell)")
    mo.ui.table(rows_q)
    return cell_q, cell_a


@app.cell
def _wilcoxon(trials, scores):
    from scipy.stats import wilcoxon

    diffs_q, diffs_a = [], []
    for hid in ("H1", "H2", "H3", "H4"):
        for idx in range(5):
            l0 = next(
                u for u, t in trials.items()
                if t["hid"] == hid and t["level"] == 0 and t["trial_index"] == idx
            )
            l3 = next(
                u for u, t in trials.items()
                if t["hid"] == hid and t["level"] == 3 and t["trial_index"] == idx
            )
            q0 = (scores[l0]["scorer_a"]["q_quant"] + scores[l0]["scorer_b"]["q_quant"]) / 2
            q3 = (scores[l3]["scorer_a"]["q_quant"] + scores[l3]["scorer_b"]["q_quant"]) / 2
            a0 = (scores[l0]["scorer_a"]["q_aware"] + scores[l0]["scorer_b"]["q_aware"]) / 2
            a3 = (scores[l3]["scorer_a"]["q_aware"] + scores[l3]["scorer_b"]["q_aware"]) / 2
            diffs_q.append(q3 - q0)
            diffs_a.append(a3 - a0)

    # H_main: one-sided Wilcoxon (L3 > L0)
    res_main = wilcoxon(diffs_q, alternative="greater", zero_method="wilcox")
    # H_null: two-sided on Q_aware
    res_null = wilcoxon(diffs_a, alternative="two-sided", zero_method="wilcox")

    mo.md(
        f"""
        ## Pre-registered hypothesis tests

        **H_main** (one-sided Wilcoxon, L3 > L0, on Q_quant)
        - statistic: {res_main.statistic:.2f}
        - p-value: {res_main.pvalue:.4g}
        - effect size (mean L3 - L0): {statistics.mean(diffs_q):.3f}
        - pre-registered criteria: p < 0.05 **and** effect ≥ 0.4
        - **decision**: {'SUPPORTED' if (res_main.pvalue < 0.05 and statistics.mean(diffs_q) >= 0.4) else 'NOT SUPPORTED'}

        **H_null** (two-sided Wilcoxon on Q_aware)
        - statistic: {res_null.statistic:.2f}
        - p-value: {res_null.pvalue:.4g}
        - effect: {statistics.mean(diffs_a):.3f}
        - pre-registered expectation: no significant difference (ceiling)
        """
    )
    return diffs_q, diffs_a


@app.cell
def _kappa(trials, scores):
    from sklearn.metrics import cohen_kappa_score

    a_q = [scores[u]["scorer_a"]["q_quant"] for u in trials]
    b_q = [scores[u]["scorer_b"]["q_quant"] for u in trials]
    a_a = [scores[u]["scorer_a"]["q_aware"] for u in trials]
    b_a = [scores[u]["scorer_b"]["q_aware"] for u in trials]

    kq = cohen_kappa_score(a_q, b_q)
    ka = cohen_kappa_score(a_a, b_a)
    agree_q = sum(1 for x, y in zip(a_q, b_q) if x == y) / len(a_q)
    agree_a = sum(1 for x, y in zip(a_a, b_a) if x == y) / len(a_a)

    mo.md(
        f"""
        ## Inter-rater reliability

        |  | agreement | Cohen's κ |
        |---|---|---|
        | Q_quant | {agree_q:.2%} | {kq:.3f} |
        | Q_aware | {agree_a:.2%} | {ka:.3f} |
        """
    )
    return


@app.cell
def _bootstrap(diffs_q):
    import random
    rng = random.Random(42)
    n = len(diffs_q)
    boots = []
    for _ in range(10000):
        sample = [diffs_q[rng.randrange(n)] for _ in range(n)]
        boots.append(statistics.mean(sample))
    boots.sort()
    lo = boots[int(0.025 * len(boots))]
    hi = boots[int(0.975 * len(boots))]
    mo.md(
        f"""
        ## Bootstrap 95% CI on effect size

        Mean L3 - L0 on Q_quant: **{statistics.mean(diffs_q):.3f}**
        95% CI: [{lo:.3f}, {hi:.3f}] (10,000 resamples, seed 42)
        """
    )
    return


if __name__ == "__main__":
    app.run()
