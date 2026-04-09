"""RDF vs Natural Language comparison experiment runner."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from rich.console import Console

from ontoprobe.db.connection import get_connection
from ontoprobe.db.introspect import format_schema_context, get_tables
from ontoprobe.hypotheses.demo import DEMO_HYPOTHESES, verify_demo
from ontoprobe.hypotheses.llm_backend import call_claude_code, extract_json
from ontoprobe.hypotheses.models import Hypothesis, VerificationResult
from ontoprobe.hypotheses.templates import HYPOTHESIS_GENERATION_PROMPT, SYSTEM_PROMPT, VERIFICATION_PROMPT
from ontoprobe.hypotheses.verifier import execute_query
from ontoprobe.ontology.loader import load_ontology
from ontoprobe.ontology.natural_language import format_doc_context, format_memo_context, format_nl_context
from ontoprobe.ontology.query import (
    format_ontology_context,
    get_causal_rules,
    get_metric_mappings,
)
from ontoprobe.semantic.manifest import format_manifest_context, load_manifest
from ontoprobe.semantic.metrics import format_metrics_context, load_metrics

console = Console()


class Condition(str, Enum):
    RDF = "rdf"
    NL = "nl"
    MEMO = "memo"
    DOC = "doc"


@dataclass
class TrialResult:
    condition: Condition
    trial_id: int
    rule_name: str
    expected_verdict: str
    llm_verdict: str
    llm_evidence: str
    is_correct: bool


@dataclass
class ConditionSummary:
    condition: Condition
    num_trials: int
    trials: list[TrialResult] = field(default_factory=list)

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
        """Fraction of trials with the modal verdict per rule."""
        from collections import Counter

        rules: dict[str, list[str]] = {}
        for t in self.trials:
            rules.setdefault(t.rule_name, []).append(t.llm_verdict)
        result = {}
        for name, verdicts in rules.items():
            most_common_count = Counter(verdicts).most_common(1)[0][1]
            result[name] = most_common_count / len(verdicts)
        return result


def _assemble_shared_context() -> tuple[str, str, str]:
    """Assemble DB and semantic layer context (shared across conditions)."""
    conn = get_connection()
    tables = get_tables(conn)
    db_context = format_schema_context(tables)
    conn.close()

    models = load_manifest()
    metrics = load_metrics()
    semantic_context = format_manifest_context(models)
    metrics_context = format_metrics_context(metrics)

    return db_context, semantic_context, metrics_context


def _build_ontology_contexts() -> dict[Condition, str]:
    """Build ontology context for each condition from the same source data."""
    graph = load_ontology()
    rules = get_causal_rules(graph)
    mappings = get_metric_mappings(graph)

    return {
        Condition.RDF: format_ontology_context(rules, mappings),
        Condition.NL: format_nl_context(rules, mappings),
        Condition.MEMO: format_memo_context(rules, mappings),
        Condition.DOC: format_doc_context(rules, mappings),
    }


def _get_ground_truth() -> dict[str, str]:
    """Execute demo hypotheses and get ground-truth verdicts."""
    conn = get_connection()
    ground_truth: dict[str, str] = {}
    for h in DEMO_HYPOTHESES:
        query_result = execute_query(conn, h.sql_query)
        result = verify_demo(h, query_result)
        ground_truth[h.ontology_rule] = result.verdict
    conn.close()
    return ground_truth


def _match_rule_name(llm_rule: str, demo_rules: list[str]) -> str | None:
    """Best-effort match of LLM-generated rule name to demo rule name."""
    llm_lower = llm_rule.lower()
    for demo_rule in demo_rules:
        if demo_rule.lower() in llm_lower or llm_lower in demo_rule.lower():
            return demo_rule
    # Keyword fallback
    keywords = {
        "discount": ["Discount increases order volume", "Discounts reduce effective margin"],
        "vip": ["VIP customers have higher AOV"],
        "seasonal": ["Seasonal products spike in Q4"],
        "q4": ["Q4 has highest overall revenue", "Seasonal products spike in Q4"],
        "free shipping": ["Free shipping increases order volume"],
        "shipping": ["Free shipping increases order volume"],
        "repeat": ["Repeat purchases correlate with CLV"],
        "clv": ["Repeat purchases correlate with CLV"],
        "ltv": ["Repeat purchases correlate with CLV"],
        "margin": ["Discounts reduce effective margin"],
    }
    for kw, candidates in keywords.items():
        if kw in llm_lower:
            for c in candidates:
                if c in demo_rules:
                    return c
    return None


def _generate_hypotheses_cc(
    db_context: str,
    semantic_context: str,
    metrics_context: str,
    ontology_context: str,
) -> list[Hypothesis]:
    """Generate hypotheses using Claude Code CLI."""
    system = SYSTEM_PROMPT.format(
        db_context=db_context,
        semantic_context=semantic_context,
        metrics_context=metrics_context,
        ontology_context=ontology_context,
    )
    text = call_claude_code(HYPOTHESIS_GENERATION_PROMPT, system=system)
    data = extract_json(text)
    return [Hypothesis(**h) for h in data["hypotheses"]]


def _verify_hypothesis_cc(
    hypothesis: Hypothesis,
    query_result: list[dict],
) -> VerificationResult:
    """Verify a hypothesis using Claude Code CLI."""
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


def run_comparison(num_trials: int = 5) -> dict[Condition, ConditionSummary]:
    """Run the RDF vs NL comparison experiment using Claude Code CLI.

    For each condition and trial:
    1. Generate hypotheses via Claude Code
    2. Execute SQL and verify via Claude Code
    3. Compare LLM verdict to demo ground truth
    """
    console.print("[bold]RDF vs NL Comparison Experiment (Claude Code)[/]")
    console.print(f"Trials per condition: {num_trials}\n")

    # Shared context (assembled once)
    console.print("[blue]Assembling shared context...[/]")
    db_context, semantic_context, metrics_context = _assemble_shared_context()

    # Condition-specific ontology contexts
    ontology_contexts = _build_ontology_contexts()

    # Ground truth from demo verification
    console.print("[blue]Computing ground truth verdicts...[/]")
    ground_truth = _get_ground_truth()
    demo_rules = list(ground_truth.keys())
    console.print(f"  Ground truth: {ground_truth}\n")

    # Run trials
    summaries: dict[Condition, ConditionSummary] = {}

    for condition in Condition:
        console.print(f"[bold blue]Condition: {condition.value.upper()}[/]")
        summary = ConditionSummary(condition=condition, num_trials=num_trials)
        ontology_context = ontology_contexts[condition]

        conn = get_connection()

        for trial_id in range(1, num_trials + 1):
            console.print(f"\n  [dim]Trial {trial_id}/{num_trials}[/]")

            # Generate hypotheses via Claude Code CLI
            try:
                hypotheses = _generate_hypotheses_cc(
                    db_context, semantic_context, metrics_context, ontology_context,
                )
            except Exception as e:
                console.print(f"    [red]Generation failed: {e}[/]")
                continue

            matched_rules: set[str] = set()

            for h in hypotheses:
                # Match to demo rule
                matched = _match_rule_name(h.ontology_rule, demo_rules)
                if not matched or matched in matched_rules:
                    continue
                matched_rules.add(matched)

                # Execute SQL
                query_result = execute_query(conn, h.sql_query)
                if query_result and "error" in query_result[0]:
                    console.print(f"    [red]SQL error for {matched}: {query_result[0]['error'][:60]}[/]")
                    continue

                # LLM verification via Claude Code CLI
                try:
                    result = _verify_hypothesis_cc(h, query_result)
                except Exception as e:
                    console.print(f"    [red]Verification failed for {matched}: {e}[/]")
                    continue

                expected = ground_truth[matched]
                trial = TrialResult(
                    condition=condition,
                    trial_id=trial_id,
                    rule_name=matched,
                    expected_verdict=expected,
                    llm_verdict=result.verdict,
                    llm_evidence=result.evidence_summary,
                    is_correct=(result.verdict == expected),
                )
                summary.trials.append(trial)

                mark = "[green]OK[/]" if trial.is_correct else "[red]NG[/]"
                console.print(
                    f"    {mark} {matched[:40]}: "
                    f"LLM={result.verdict} vs GT={expected}"
                )

        conn.close()
        summaries[condition] = summary
        console.print(f"\n  [bold]Accuracy: {summary.accuracy:.1%}[/]")

    # Generate report
    from ontoprobe.evaluation.comparison_report import generate_comparison_report

    generate_comparison_report(summaries, ground_truth)

    return summaries
