"""Measure LLM prior for each basic causal rule.

Phase 10 Step 1: outside the agent loop, ask the LLM what it would expect
based on general e-commerce knowledge for each of the 7 basic 1-hop
causal rules in the ontology. The LLM is never shown the ontology's own
prediction; it only sees a neutrally-phrased question.

Each rule is queried 3 times (to account for stochasticity) and the
majority direction is compared against the ontology's direction to
classify the rule as:

    aligned        — LLM agrees with ontology direction
    weak           — LLM says "unclear" or "no_effect"
    contradicting  — LLM says the opposite direction

Outputs the classification matrix and saves raw samples to
data/rootcause/llm_prior_measurement.json, which is used in Phase 10
Step 2 to decide which rules to invert in the contradiction experiment.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console(width=130)

SANDBOX = Path("/tmp")
MODEL = "sonnet"
N_SAMPLES = 3
MAX_RETRIES = 3
RESULTS_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "rootcause"
    / "llm_prior_measurement.json"
)


@dataclass
class PriorQuery:
    rule_id: str
    cause: str
    effect: str
    ontology_direction: str
    ontology_magnitude: str
    question: str


BASIC_RULES: list[PriorQuery] = [
    PriorQuery(
        rule_id="rule_discount_order_volume",
        cause="Discount Campaign",
        effect="Order Volume",
        ontology_direction="increase",
        ontology_magnitude="+15-30%",
        question=(
            "In typical e-commerce, when a discount campaign with >10% off is "
            "active (compared to non-campaign days), does the daily number of "
            "orders typically increase or decrease, and by roughly how much?"
        ),
    ),
    PriorQuery(
        rule_id="rule_seasonal_revenue",
        cause="Seasonal Product",
        effect="Seasonal Revenue",
        ontology_direction="increase",
        ontology_magnitude="2-3x in Q4",
        question=(
            "In typical e-commerce, during Q4 (October–December, including the "
            "holiday season) compared to other quarters, does revenue from "
            "seasonal products (winter fashion, gift sets, holiday items) "
            "typically increase or decrease, and by roughly how much?"
        ),
    ),
    PriorQuery(
        rule_id="rule_vip_higher_aov",
        cause="VIP Customer",
        effect="Average Order Value",
        ontology_direction="increase",
        ontology_magnitude="+40-60%",
        question=(
            "In typical e-commerce, do VIP (high-value, loyalty-tier) customers "
            "have a higher or lower average order value compared to new "
            "(first-time) customers, and by roughly how much?"
        ),
    ),
    PriorQuery(
        rule_id="rule_free_shipping_volume",
        cause="Free Shipping Campaign",
        effect="Order Volume",
        ontology_direction="increase",
        ontology_magnitude="+10-20%",
        question=(
            "In typical e-commerce, when a free-shipping campaign is running "
            "(compared to no campaign), does daily order volume typically "
            "increase or decrease, and by roughly how much?"
        ),
    ),
    PriorQuery(
        rule_id="rule_q4_overall_revenue",
        cause="Seasonal Product (Q4)",
        effect="Total Revenue",
        ontology_direction="increase",
        ontology_magnitude="+30-50%",
        question=(
            "In typical e-commerce, is total Q4 (October–December) revenue "
            "higher or lower than an average quarter, and by roughly how much?"
        ),
    ),
    PriorQuery(
        rule_id="rule_discount_reduces_margin",
        cause="Discount Campaign",
        effect="Effective Margin",
        ontology_direction="decrease",
        ontology_magnitude="proportional to discount percent",
        question=(
            "In typical e-commerce, when a discount campaign is running (with "
            ">10% off), does the effective profit margin (revenue after "
            "discounts divided by gross revenue) increase or decrease, and by "
            "roughly how much?"
        ),
    ),
    PriorQuery(
        rule_id="rule_repeat_clv",
        cause="Repeat Purchase Rate",
        effect="Customer Lifetime Value",
        ontology_direction="increase",
        ontology_magnitude="positive correlation",
        question=(
            "In typical e-commerce, do customers with higher repeat-purchase "
            "rates have higher or lower lifetime value, and how strong is the "
            "relationship?"
        ),
    ),
]


SYSTEM_PROMPT = """You are an experienced e-commerce data analyst. Based on general industry knowledge (not specific to any single company), answer the user's question about typical business relationships.

Respond with EXACTLY ONE JSON object inside a ```json code fence:

```json
{
    "direction": "increase" | "decrease" | "unclear" | "no_effect",
    "typical_magnitude": "<short phrase like '+15-30%' or 'unclear' if you don't have a typical expectation>",
    "confidence": "high" | "medium" | "low",
    "reasoning": "<one short sentence>"
}
```

No preamble, no additional text outside the JSON block.
"""


def _claude_query(prompt: str) -> dict | None:
    cmd = [
        "claude",
        "-p",
        "--output-format",
        "json",
        "--tools",
        "",
        "--model",
        MODEL,
        "--no-session-persistence",
        "--system-prompt",
        SYSTEM_PROMPT,
    ]
    for attempt in range(MAX_RETRIES):
        try:
            completed = subprocess.run(
                cmd,
                input=prompt,
                cwd=str(SANDBOX),
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            continue
        if completed.returncode != 0:
            continue
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            continue
        text = payload.get("result", "")
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if not m:
            m = re.search(r"(\{[^{}]*\"direction\"[^{}]*\})", text, re.DOTALL)
        if not m:
            continue
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
    return None


def classify(llm_direction: str, ontology_direction: str) -> str:
    if llm_direction in ("unclear", "no_effect", "unknown"):
        return "weak"
    if llm_direction == ontology_direction:
        return "aligned"
    return "contradicting"


def main() -> None:
    console.print(
        "[bold]Measuring LLM prior for 7 basic causal rules "
        f"({N_SAMPLES} samples each)[/]\n"
    )

    all_results: list[dict] = []
    for q in BASIC_RULES:
        console.print(
            f"[bold cyan]{q.rule_id}[/]: {q.cause} → {q.effect}  "
            f"[dim](ontology: {q.ontology_direction}, {q.ontology_magnitude})[/]"
        )
        samples: list[dict] = []
        for i in range(N_SAMPLES):
            r = _claude_query(q.question)
            if r is None:
                console.print(f"  sample {i + 1}: [red]FAILED[/]")
                continue
            samples.append(r)
            console.print(
                f"  sample {i + 1}: direction={r.get('direction', '?'):12} "
                f"magnitude={r.get('typical_magnitude', '?'):20} "
                f"conf={r.get('confidence', '?')}"
            )

        directions = [s.get("direction") for s in samples if s]
        majority = (
            Counter(directions).most_common(1)[0][0]
            if directions
            else "unknown"
        )
        cls = classify(majority, q.ontology_direction)
        all_results.append(
            {
                "rule_id": q.rule_id,
                "cause": q.cause,
                "effect": q.effect,
                "ontology_direction": q.ontology_direction,
                "ontology_magnitude": q.ontology_magnitude,
                "llm_majority_direction": majority,
                "llm_samples": samples,
                "classification": cls,
            }
        )
        console.print(
            f"  → [bold]majority={majority}[/] "
            f"classification=[{'green' if cls == 'aligned' else 'yellow' if cls == 'weak' else 'red'}]{cls}[/]\n"
        )

    # Summary table
    table = Table(title="\nLLM prior vs ontology", show_lines=True)
    table.add_column("Rule", style="bold")
    table.add_column("Ontology (dir / mag)")
    table.add_column("LLM (majority dir)", justify="center")
    table.add_column("LLM magnitudes (samples)")
    table.add_column("Class")

    for r in all_results:
        cls = r["classification"]
        color = {
            "aligned": "green",
            "weak": "yellow",
            "contradicting": "red",
        }[cls]
        mags = " | ".join(
            s.get("typical_magnitude", "?") for s in r["llm_samples"]
        )
        table.add_row(
            f"{r['cause']} → {r['effect']}",
            f"{r['ontology_direction']} / {r['ontology_magnitude']}",
            r["llm_majority_direction"],
            mags,
            f"[{color}]{cls}[/]",
        )
    console.print(table)

    # Aggregate
    counts = Counter(r["classification"] for r in all_results)
    console.print(
        f"\n[bold]Summary:[/] "
        f"aligned {counts.get('aligned', 0)} / "
        f"weak {counts.get('weak', 0)} / "
        f"contradicting {counts.get('contradicting', 0)} "
        f"of {len(all_results)} rules"
    )

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    console.print(f"\n[dim]Saved to {RESULTS_PATH}[/]")


if __name__ == "__main__":
    main()
