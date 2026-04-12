"""Confirmatory mini-study infrastructure.

Pre-registered protocol: reports/confirmatory_protocol.md (commit c76a2a8).
Implements runner prompt builders, blind scorer prompts, and trial I/O.
This module is LLM-agnostic: it produces prompts + parses results. Actual
LLM invocation is done by the orchestrator via Claude Code subagents.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "confirmatory"


@dataclass(frozen=True)
class HypothesisFixture:
    """A (hypothesis, pre-computed query result) pair for confirmatory trials.

    Query results are pre-computed to eliminate SQL-execution variance between
    trials. The only variable in the study is L0 vs L3 context + LLM stochasticity.

    Critical design decision: `claim` is DIRECTIONAL ONLY. It does not contain
    the expected magnitude (e.g., no "30-50%"). The magnitude is injected ONLY
    via the L3 ontology block. Otherwise the L0 condition would trivially pass
    the Q_quant rubric by comparing observed values to the magnitude embedded
    in the claim itself, defeating the L0 vs L3 contrast.
    """

    hid: str  # "H1", "H2", "H3", "H4"
    claim: str  # Directional claim, magnitude-free
    query_sql: str
    query_result_table: str  # Pre-formatted markdown-ish table
    expected_direction: str  # "increase" / "decrease"
    l3_expected_magnitude: str  # What L3 ontology reveals


FIXTURES: dict[str, HypothesisFixture] = {
    "H1": HypothesisFixture(
        hid="H1",
        claim="Q4 revenue is higher than the average of Q1-Q3 revenue.",
        query_sql=(
            "SELECT order_quarter, SUM(total_amount) AS quarterly_revenue, "
            "COUNT(*) AS order_count, AVG(total_amount) AS avg_order_value "
            "FROM fct_orders GROUP BY order_quarter ORDER BY order_quarter"
        ),
        query_result_table=(
            "| order_quarter | quarterly_revenue | order_count | avg_order_value |\n"
            "|---|---|---|---|\n"
            "| 1 | 5,148,206 | 469 | 10,976.99 |\n"
            "| 2 | 6,181,726 | 528 | 11,707.81 |\n"
            "| 3 | 5,486,749 | 536 | 10,236.47 |\n"
            "| 4 | 11,014,309 | 785 | 14,030.97 |"
        ),
        expected_direction="increase",
        l3_expected_magnitude="30-50%",
    ),
    "H2": HypothesisFixture(
        hid="H2",
        claim="Daily orders during discount campaigns are higher than on non-campaign days.",
        query_sql=(
            "WITH daily_orders AS (SELECT order_date, has_campaign, COUNT(*) AS daily_order_count "
            "FROM fct_orders GROUP BY order_date, has_campaign) "
            "SELECT has_campaign, AVG(daily_order_count) AS avg_daily_orders, "
            "COUNT(*) AS num_days FROM daily_orders GROUP BY has_campaign"
        ),
        query_result_table=(
            "| has_campaign | avg_daily_orders | num_days |\n"
            "|---|---|---|\n"
            "| false | 6.259 | 293 |\n"
            "| true  | 6.722 |  72 |"
        ),
        expected_direction="increase",
        l3_expected_magnitude="15-30%",
    ),
    "H3": HypothesisFixture(
        hid="H3",
        claim="VIP customers' average order value is higher than New customers' average order value.",
        query_sql=(
            "SELECT customer_segment, AVG(total_amount) AS avg_order_value, "
            "COUNT(*) AS order_count, SUM(total_amount) AS total_revenue "
            "FROM fct_orders WHERE customer_segment IN ('vip','new') GROUP BY customer_segment"
        ),
        query_result_table=(
            "| customer_segment | avg_order_value | order_count | total_revenue |\n"
            "|---|---|---|---|\n"
            "| new |  6,174.40 | 1,283 |  7,921,750 |\n"
            "| vip | 43,288.75 |   306 | 13,246,359 |"
        ),
        expected_direction="increase",
        l3_expected_magnitude="40-60%",
    ),
    "H4": HypothesisFixture(
        hid="H4",
        claim="Q4 seasonal-product revenue is higher than the Q1-Q3 average of seasonal-product revenue.",
        query_sql=(
            "SELECT order_quarter, "
            "SUM(CASE WHEN is_seasonal THEN line_total ELSE 0 END) AS seasonal_revenue, "
            "SUM(CASE WHEN NOT is_seasonal THEN line_total ELSE 0 END) AS evergreen_revenue, "
            "SUM(line_total) AS total_item_revenue FROM fct_order_items "
            "GROUP BY order_quarter ORDER BY order_quarter"
        ),
        query_result_table=(
            "| order_quarter | seasonal_revenue | evergreen_revenue | total_item_revenue |\n"
            "|---|---|---|---|\n"
            "| 1 |    305,030 | 4,843,176 |  5,148,206 |\n"
            "| 2 |    631,870 | 5,549,856 |  6,181,726 |\n"
            "| 3 |    355,732 | 5,571,304 |  5,927,036 |\n"
            "| 4 |  6,453,118 | 5,216,282 | 11,669,400 |"
        ),
        expected_direction="increase",
        l3_expected_magnitude="2-3x",
    ),
}


L3_ONTOLOGY_SNIPPET = """\
## Domain Knowledge (Ontology)

### Class Hierarchy
- Customer → NewCustomer / ReturningCustomer / VIPCustomer
- Product → SeasonalProduct / EvergreenProduct
- Campaign → DiscountCampaign / FreeShippingCampaign

### Causal Rules (with expected magnitude)

**Rule: Q4 has highest overall revenue**
  - Cause: Seasonal Product
  - Effect on: Revenue
  - Direction: increase
  - Expected magnitude: 30-50%

**Rule: Discount increases order volume**
  - Cause: Discount Campaign
  - Effect on: Order Volume
  - Direction: increase
  - Expected magnitude: 15-30%

**Rule: VIP customers have higher AOV**
  - Cause: VIP Customer
  - Effect on: Average Order Value
  - Direction: increase
  - Expected magnitude: 40-60%

**Rule: Seasonal products spike in Q4**
  - Cause: Seasonal Product
  - Effect on: Seasonal Revenue
  - Direction: increase
  - Expected magnitude: 2-3x
"""


def build_runner_prompt(fixture: HypothesisFixture, level: int) -> str:
    """Build the analysis prompt shown to the runner LLM for one trial.

    level=0 → no ontology context (baseline)
    level=3 → class hierarchy + causal rules + expected magnitudes
    """
    if level not in (0, 3):
        raise ValueError(f"Confirmatory study uses only L0/L3, got L{level}")

    header = (
        "You are a data analyst analyzing an e-commerce database.\n"
        "A hypothesis has been tested via the SQL query below, and the query result is provided.\n"
        "Analyze whether the data supports, contradicts, or is inconclusive for the hypothesis.\n"
    )

    ontology_block = L3_ONTOLOGY_SNIPPET if level == 3 else ""

    task = f"""
**Hypothesis:** {fixture.claim}

**SQL Query:**
```sql
{fixture.query_sql}
```

**Query Result:**
{fixture.query_result_table}

Provide your analysis. Discuss what the data shows, how it relates to the hypothesis,
and give a final verdict. Return your response as JSON with this schema:
```json
{{
  "analysis": "Your full reasoning (multi-paragraph OK)",
  "verdict": "supported" | "contradicted" | "inconclusive",
  "evidence_summary": "One-sentence summary"
}}
```
Return ONLY the JSON, no other text.
"""
    if ontology_block:
        return f"{header}\n{ontology_block}\n{task}"
    return f"{header}\n{task}"


# ---------- Blind scorer ----------

SCORER_SYSTEM = """\
You are an impartial rubric scorer. You will be shown one LLM analysis of a
data hypothesis. Your job is to apply the rubric below mechanically and return
two independent 0/1 judgments.

You do NOT know (and should not try to infer) which experimental condition the
analysis came from. Do not reward or penalize based on whether it "sounds like"
the LLM had extra context. Score only what is explicitly present in the text.
"""

SCORER_RUBRIC = """\
## Rubric (each judgment is independent, 0 or 1)

### Q_quant — Quantitative deviation detection
Score 1 if ALL of the following hold:
  (a) The analysis explicitly compares the observed value to an "expected",
      "baseline", "typical", or "assumed" value.
  (b) The comparison is quantitative: it names an explicit deviation such as
      "N times larger", "N% above expected", "N-fold deviation", etc.
  (c) The direction of the deviation (above/below expectation) matches what
      the data actually shows.
Otherwise score 0.

**Critical:** If the analysis invents its own baseline from prior knowledge
(e.g., "a naive baseline would assume 10-30%") WITHOUT that baseline being
given in the prompt, score 0. Fabricated baselines do not count.

### Q_aware — Situation awareness
Score 1 if BOTH:
  (a) The analysis correctly summarizes the numerical values in the query result
      (no misreads of magnitudes, directions, or which row is which).
  (b) The analysis provides a verdict: supported / contradicted / inconclusive.
Otherwise score 0.
"""

SCORER_OUTPUT_SPEC = """\
Return your judgment as JSON:
```json
{
  "q_quant": 0 | 1,
  "q_quant_rationale": "One-sentence justification citing the relevant text",
  "q_aware": 0 | 1,
  "q_aware_rationale": "One-sentence justification"
}
```
Return ONLY the JSON.
"""


def build_scorer_prompt(masked_analysis_text: str) -> tuple[str, str]:
    """Return (system, user) prompts for a blind scorer.

    The scorer sees only the LLM output text. No hypothesis ID, no level label,
    no ground truth. The system prompt tells it to score mechanically.
    """
    user = (
        f"{SCORER_RUBRIC}\n"
        f"---\n"
        f"## Analysis to score\n"
        f"```\n{masked_analysis_text}\n```\n"
        f"---\n"
        f"{SCORER_OUTPUT_SPEC}"
    )
    return SCORER_SYSTEM, user


def mask_for_scorer(analysis_text: str) -> str:
    """Pass-through mask.

    Per protocol §6, we mask file-level metadata (which is handled by how we
    pass data to the scorer — we simply don't include level/hid), not the
    LLM output body. The output body may still contain the hypothesis subject
    (e.g., "VIP", "Q4") because that is the analysis itself.
    """
    return analysis_text.strip()


# ---------- Trial I/O ----------


@dataclass
class TrialRecord:
    trial_uuid: str
    hid: str
    level: int
    trial_index: int  # 0..n-1 within the cell
    runner_prompt: str
    runner_raw_output: str
    runner_json: dict = field(default_factory=dict)
    runner_model: str = "claude-opus-4-6"
    error: str | None = None

    def save(self, data_dir: Path = DATA_DIR) -> Path:
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / f"trial_{self.trial_uuid}.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path: Path) -> TrialRecord:
        return cls(**json.loads(path.read_text()))


@dataclass
class ScoreRecord:
    trial_uuid: str
    scorer_id: str  # "scorer_a" / "scorer_b" / "scorer_c"
    q_quant: int
    q_quant_rationale: str
    q_aware: int
    q_aware_rationale: str

    def save(self, data_dir: Path = DATA_DIR) -> Path:
        score_dir = data_dir / "scores"
        score_dir.mkdir(parents=True, exist_ok=True)
        path = score_dir / f"score_{self.trial_uuid}_{self.scorer_id}.json"
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))
        return path


def new_trial_uuid() -> str:
    return uuid.uuid4().hex[:12]


def planned_trials(n_per_cell: int = 5) -> list[tuple[str, int, int]]:
    """Return the full list of (hid, level, trial_index) tuples per the protocol."""
    return [
        (hid, level, idx)
        for hid in ("H1", "H2", "H3", "H4")
        for level in (0, 3)
        for idx in range(n_per_cell)
    ]
