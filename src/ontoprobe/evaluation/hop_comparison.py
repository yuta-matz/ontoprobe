"""Hop-count comparison: measure how chain depth affects LLM accuracy across formats."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from rich.console import Console

from ontoprobe.db.connection import get_connection
from ontoprobe.db.introspect import format_schema_context, get_tables
from ontoprobe.hypotheses.demo import (
    CHAIN_HYPOTHESES,
    DEMO_HYPOTHESES,
    FIVE_HOP_HYPOTHESES,
    FOUR_HOP_HYPOTHESES,
    THREE_HOP_HYPOTHESES,
    verify_demo,
)
from ontoprobe.hypotheses.llm_backend import call_claude_code, extract_json
from ontoprobe.hypotheses.models import Hypothesis, VerificationResult
from ontoprobe.hypotheses.templates import (
    HYPOTHESIS_GENERATION_PROMPT,
    SYSTEM_PROMPT,
    VERIFICATION_PROMPT,
)
from ontoprobe.hypotheses.verifier import execute_query
from ontoprobe.ontology.loader import load_ontology
from ontoprobe.ontology.natural_language import (
    format_doc_context,
    format_memo_context,
    format_nl_context,
)
from ontoprobe.ontology.query import format_ontology_context, get_causal_rules, get_metric_mappings
from ontoprobe.semantic.manifest import format_manifest_context, load_manifest
from ontoprobe.semantic.metrics import format_metrics_context, load_metrics

console = Console()


class HopLevel(str, Enum):
    HOP_1 = "1-hop"
    HOP_2 = "2-hop"
    HOP_3 = "3-hop"
    HOP_4 = "4-hop"
    HOP_5 = "5-hop"


class Format(str, Enum):
    RDF = "rdf"
    NL = "nl"
    MEMO = "memo"
    DOC = "doc"


# Map hop levels to their demo hypotheses
HOP_HYPOTHESES: dict[HopLevel, list[Hypothesis]] = {
    HopLevel.HOP_1: DEMO_HYPOTHESES,
    HopLevel.HOP_2: CHAIN_HYPOTHESES,
    HopLevel.HOP_3: THREE_HOP_HYPOTHESES,
    HopLevel.HOP_4: FOUR_HOP_HYPOTHESES,
    HopLevel.HOP_5: FIVE_HOP_HYPOTHESES,
}


@dataclass
class HopTrialResult:
    fmt: Format
    hop_level: HopLevel
    trial_id: int
    rule_name: str
    expected_verdict: str
    llm_verdict: str
    llm_evidence: str
    is_correct: bool


# Key: (format, hop_level) -> summary
CellKey = tuple[Format, HopLevel]


@dataclass
class HopLevelSummary:
    fmt: Format
    hop_level: HopLevel
    num_trials: int
    trials: list[HopTrialResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if not self.trials:
            return 0.0
        return sum(1 for t in self.trials if t.is_correct) / len(self.trials)

    @property
    def per_rule_accuracy(self) -> dict[str, float]:
        rules: dict[str, list[bool]] = {}
        for t in self.trials:
            rules.setdefault(t.rule_name, []).append(t.is_correct)
        return {name: sum(v) / len(v) for name, v in rules.items()}

    @property
    def consistency(self) -> dict[str, float]:
        from collections import Counter

        rules: dict[str, list[str]] = {}
        for t in self.trials:
            rules.setdefault(t.rule_name, []).append(t.llm_verdict)
        result = {}
        for name, verdicts in rules.items():
            most_common_count = Counter(verdicts).most_common(1)[0][1]
            result[name] = most_common_count / len(verdicts)
        return result

    @property
    def coverage(self) -> float:
        gt = HOP_HYPOTHESES[self.hop_level]
        gt_rules = {h.ontology_rule for h in gt}
        matched = {t.rule_name for t in self.trials}
        return len(matched & gt_rules) / len(gt_rules) if gt_rules else 0


def _assemble_shared_context() -> tuple[str, str, str]:
    """Assemble DB and semantic layer context."""
    conn = get_connection()
    tables = get_tables(conn)
    db_context = format_schema_context(tables)
    conn.close()

    models = load_manifest()
    metrics = load_metrics()
    semantic_context = format_manifest_context(models)
    metrics_context = format_metrics_context(metrics)

    return db_context, semantic_context, metrics_context


def _build_format_contexts() -> dict[Format, str]:
    """Build ontology context for each format."""
    graph = load_ontology()
    rules = get_causal_rules(graph)
    mappings = get_metric_mappings(graph)

    return {
        Format.RDF: format_ontology_context(rules, mappings),
        Format.NL: format_nl_context(rules, mappings),
        Format.MEMO: format_memo_context(rules, mappings),
        Format.DOC: format_doc_context(rules, mappings),
    }


def _get_ground_truth(hop_level: HopLevel) -> dict[str, str]:
    conn = get_connection()
    ground_truth: dict[str, str] = {}
    for h in HOP_HYPOTHESES[hop_level]:
        query_result = execute_query(conn, h.sql_query)
        result = verify_demo(h, query_result)
        ground_truth[h.ontology_rule] = result.verdict
    conn.close()
    return ground_truth


_MATCH_KEYWORDS_1HOP: dict[str, list[str]] = {
    "Q4 has highest overall revenue": ["q4", "overall revenue", "highest revenue"],
    "Discount increases order volume": ["discount", "order volume"],
    "VIP customers have higher AOV": ["vip", "aov", "average order"],
    "Seasonal products spike in Q4": ["seasonal", "spike", "q4"],
    "Free shipping increases order volume": ["free shipping", "shipping"],
    "Repeat purchases correlate with CLV": ["repeat", "clv", "ltv", "lifetime"],
    "Discounts reduce effective margin": ["discount", "margin"],
}

_MATCH_KEYWORDS_2HOP: dict[str, list[str]] = {
    "Discount drives revenue through order volume": ["discount", "revenue", "order volume"],
    "Discount erodes effective margin through discount amount": ["discount", "margin", "erode"],
    "VIP customers drive revenue through higher AOV": ["vip", "revenue", "aov"],
}

_MATCH_KEYWORDS_3HOP: dict[str, list[str]] = {
    "Seasonal spike concentrates annual revenue in Q4": ["seasonal", "concentrate", "annual", "q4 share"],
    "VIP revenue drives concentration risk": ["vip", "concentration", "risk"],
    "Discount revenue impact limits profit growth": ["discount", "profit", "growth", "limit"],
}

_MATCH_KEYWORDS_4HOP: dict[str, list[str]] = {
    "Q4 concentration creates seasonal dependency risk": ["q4", "seasonal", "dependency", "risk"],
    "VIP concentration creates segment dependency risk": ["vip", "segment", "dependency", "concentration"],
    "Negative profit growth indicates poor campaign efficiency": ["campaign", "efficiency", "profit", "negative"],
}

_MATCH_KEYWORDS_5HOP: dict[str, list[str]] = {
    "Seasonal dependency creates strategic vulnerability": ["seasonal", "strategic", "vulnerability"],
    "Segment dependency demands VIP retention priority": ["vip", "retention", "priority", "dependency"],
    "Poor campaign efficiency demands strategy revision": ["campaign", "strategy", "revision", "efficiency"],
}

_HOP_KEYWORDS = {
    HopLevel.HOP_1: _MATCH_KEYWORDS_1HOP,
    HopLevel.HOP_2: _MATCH_KEYWORDS_2HOP,
    HopLevel.HOP_3: _MATCH_KEYWORDS_3HOP,
    HopLevel.HOP_4: _MATCH_KEYWORDS_4HOP,
    HopLevel.HOP_5: _MATCH_KEYWORDS_5HOP,
}


def _match_rule(llm_rule: str, demo_rules: list[str], keywords: dict[str, list[str]]) -> str | None:
    llm_lower = llm_rule.lower()
    for demo_rule in demo_rules:
        if demo_rule.lower() in llm_lower or llm_lower in demo_rule.lower():
            return demo_rule
    for rule, kws in keywords.items():
        if rule not in demo_rules:
            continue
        matches = sum(1 for kw in kws if kw in llm_lower)
        if matches >= 2:
            return rule
    return None


def _generate_hypotheses(
    db_context: str,
    semantic_context: str,
    metrics_context: str,
    ontology_context: str,
) -> list[Hypothesis]:
    system = SYSTEM_PROMPT.format(
        db_context=db_context,
        semantic_context=semantic_context,
        metrics_context=metrics_context,
        ontology_context=ontology_context,
    )
    text = call_claude_code(HYPOTHESIS_GENERATION_PROMPT, system=system)
    data = extract_json(text)
    return [Hypothesis(**h) for h in data["hypotheses"]]


def _verify_hypothesis(
    hypothesis: Hypothesis,
    query_result: list[dict],
) -> VerificationResult:
    result_text = json.dumps(query_result, indent=2, default=str)
    if len(result_text) > 3000:
        result_text = result_text[:3000] + "\n... (truncated)"

    prompt = VERIFICATION_PROMPT.format(
        description=hypothesis.description,
        expected_direction=hypothesis.expected_direction,
        ontology_rule=hypothesis.ontology_rule,
        query_result=result_text,
    )
    text = call_claude_code(prompt)
    data = extract_json(text)
    return VerificationResult(
        hypothesis=hypothesis,
        query_result=query_result,
        verdict=data["verdict"],
        evidence_summary=data["evidence_summary"],
    )


def run_hop_comparison(
    num_trials: int = 3,
) -> dict[CellKey, HopLevelSummary]:
    """Run Format x HopLevel comparison: 4 formats x 3 hop levels.

    For each format and trial, generates hypotheses once and matches to each
    hop level's ground truth rules.
    """
    console.print("[bold]Format x Hop-Count Comparison (4 formats x 3 hops)[/]")
    console.print(f"Trials: {num_trials}\n")

    console.print("[blue]Assembling context...[/]")
    db_context, semantic_context, metrics_context = _assemble_shared_context()
    format_contexts = _build_format_contexts()

    ground_truths: dict[HopLevel, dict[str, str]] = {}
    for hop in HopLevel:
        gt = _get_ground_truth(hop)
        ground_truths[hop] = gt
        console.print(f"[blue]{hop.value} ground truth:[/] {gt}")
    console.print("")

    summaries: dict[CellKey, HopLevelSummary] = {
        (fmt, hop): HopLevelSummary(fmt=fmt, hop_level=hop, num_trials=num_trials)
        for fmt in Format
        for hop in HopLevel
    }

    conn = get_connection()

    for fmt in Format:
        console.print(f"[bold magenta]Format: {fmt.value.upper()}[/]")
        ontology_context = format_contexts[fmt]

        for trial_id in range(1, num_trials + 1):
            console.print(f"\n  [dim]Trial {trial_id}/{num_trials}[/]")

            try:
                hypotheses = _generate_hypotheses(
                    db_context, semantic_context, metrics_context, ontology_context,
                )
                console.print(f"    Generated {len(hypotheses)} hypotheses")
            except Exception as e:
                console.print(f"    [red]Generation failed: {e}[/]")
                continue

            for hop in HopLevel:
                gt = ground_truths[hop]
                demo_rules = list(gt.keys())
                keywords = _HOP_KEYWORDS[hop]
                matched_rules: set[str] = set()

                for h in hypotheses:
                    matched = _match_rule(h.ontology_rule, demo_rules, keywords)
                    if not matched or matched in matched_rules:
                        continue
                    matched_rules.add(matched)

                    query_result = execute_query(conn, h.sql_query)
                    if query_result and "error" in query_result[0]:
                        continue

                    try:
                        result = _verify_hypothesis(h, query_result)
                    except Exception:
                        continue

                    expected = gt[matched]
                    trial = HopTrialResult(
                        fmt=fmt,
                        hop_level=hop,
                        trial_id=trial_id,
                        rule_name=matched,
                        expected_verdict=expected,
                        llm_verdict=result.verdict,
                        llm_evidence=result.evidence_summary,
                        is_correct=(result.verdict == expected),
                    )
                    summaries[(fmt, hop)].trials.append(trial)

                    mark = "[green]OK[/]" if trial.is_correct else "[red]NG[/]"
                    console.print(
                        f"    {mark} [{hop.value}] {matched[:40]}: "
                        f"{result.verdict} vs {expected}"
                    )

        # Per-format summary
        console.print(f"\n  [bold]{fmt.value.upper()} Summary:[/]")
        for hop in HopLevel:
            s = summaries[(fmt, hop)]
            console.print(f"    {hop.value}: {s.accuracy:.1%} ({len(s.trials)} trials)")
        console.print("")

    conn.close()

    from ontoprobe.evaluation.hop_comparison_report import generate_hop_comparison_report

    generate_hop_comparison_report(summaries, ground_truths)

    return summaries
