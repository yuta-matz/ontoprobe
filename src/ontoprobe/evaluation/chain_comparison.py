"""RDF vs NL vs MEMO vs DOC comparison for multi-hop causal reasoning."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum

from rich.console import Console

from ontoprobe.db.connection import get_connection
from ontoprobe.db.introspect import format_schema_context, get_tables
from ontoprobe.hypotheses.demo import CHAIN_HYPOTHESES, verify_demo
from ontoprobe.hypotheses.llm_backend import call_claude_code, extract_json
from ontoprobe.hypotheses.models import Hypothesis, VerificationResult
from ontoprobe.hypotheses.templates import SYSTEM_PROMPT, VERIFICATION_PROMPT
from ontoprobe.hypotheses.verifier import execute_query
from ontoprobe.ontology.loader import load_ontology
from ontoprobe.ontology.natural_language import (
    format_doc_context,
    format_memo_context,
    format_nl_context,
)
from ontoprobe.ontology.query import (
    format_ontology_context,
    get_causal_rules,
    get_metric_mappings,
)
from ontoprobe.semantic.manifest import format_manifest_context, load_manifest
from ontoprobe.semantic.metrics import format_metrics_context, load_metrics

console = Console()


CHAIN_HYPOTHESIS_GENERATION_PROMPT = """\
Based on the domain knowledge provided, generate testable hypotheses about
multi-hop causal chains. Focus on how causes propagate through intermediate
effects (e.g., A causes B, which in turn causes C).

For each hypothesis:
1. Identify the causal chain it derives from
2. Write a specific, testable claim that covers the FULL chain (not just one hop)
3. Write DuckDB SQL that tests BOTH the intermediate step AND the final outcome
4. Identify the expected direction

Return your response as a JSON array of objects with this schema:
{{
  "hypotheses": [
    {{
      "description": "Specific testable claim about the multi-hop chain",
      "ontology_rule": "Name of the causal chain this derives from",
      "expected_direction": "increase/decrease/correlation",
      "sql_query": "SELECT ... FROM ...",
      "relevant_metrics": ["metric_name"],
      "relevant_dimensions": ["dimension_name"]
    }}
  ]
}}

Generate one hypothesis per causal chain. Make each SQL query self-contained.
Return ONLY the JSON, no other text.
"""


class ChainCondition(str, Enum):
    RDF = "rdf"
    NL = "nl"
    MEMO = "memo"
    DOC = "doc"


@dataclass
class ChainTrialResult:
    condition: ChainCondition
    trial_id: int
    rule_name: str
    expected_verdict: str
    llm_verdict: str
    llm_evidence: str
    is_correct: bool
    mentions_intermediate: bool


@dataclass
class ChainConditionSummary:
    condition: ChainCondition
    num_trials: int
    trials: list[ChainTrialResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        if not self.trials:
            return 0.0
        return sum(1 for t in self.trials if t.is_correct) / len(self.trials)

    @property
    def chain_awareness(self) -> float:
        """Fraction of trials where LLM mentions intermediate causal steps."""
        if not self.trials:
            return 0.0
        return sum(1 for t in self.trials if t.mentions_intermediate) / len(self.trials)

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


def _build_ontology_contexts() -> dict[ChainCondition, str]:
    """Build ontology context for each condition from the same source data."""
    graph = load_ontology()
    rules = get_causal_rules(graph)
    mappings = get_metric_mappings(graph)

    return {
        ChainCondition.RDF: format_ontology_context(rules, mappings),
        ChainCondition.NL: format_nl_context(rules, mappings),
        ChainCondition.MEMO: format_memo_context(rules, mappings),
        ChainCondition.DOC: format_doc_context(rules, mappings),
    }


def _get_chain_ground_truth() -> dict[str, str]:
    """Execute chain hypotheses and get ground-truth verdicts."""
    conn = get_connection()
    ground_truth: dict[str, str] = {}
    for h in CHAIN_HYPOTHESES:
        query_result = execute_query(conn, h.sql_query)
        result = verify_demo(h, query_result)
        ground_truth[h.ontology_rule] = result.verdict
    conn.close()
    return ground_truth


def _match_chain_rule(llm_rule: str, demo_rules: list[str]) -> str | None:
    """Best-effort match of LLM rule name to chain demo rule name."""
    llm_lower = llm_rule.lower()
    for demo_rule in demo_rules:
        if demo_rule.lower() in llm_lower or llm_lower in demo_rule.lower():
            return demo_rule
    keywords = {
        "discount": {
            "revenue": "Discount drives revenue through order volume",
            "margin": "Discount erodes effective margin through discount amount",
        },
        "vip": {
            "revenue": "VIP customers drive revenue through higher AOV",
            "aov": "VIP customers drive revenue through higher AOV",
        },
    }
    for entity_kw, sub_map in keywords.items():
        if entity_kw in llm_lower:
            for sub_kw, rule in sub_map.items():
                if sub_kw in llm_lower and rule in demo_rules:
                    return rule
    return None


_INTERMEDIATE_KEYWORDS = {
    "Discount drives revenue through order volume": [
        "order volume", "order count", "注文数", "注文件数", "orders",
    ],
    "Discount erodes effective margin through discount amount": [
        "discount amount", "割引額", "割引総額", "discount total",
    ],
    "VIP customers drive revenue through higher AOV": [
        "aov", "average order value", "平均注文額", "注文単価", "order value",
    ],
}


def _check_intermediate_mention(rule_name: str, evidence: str) -> bool:
    """Check if the LLM evidence mentions intermediate causal steps."""
    keywords = _INTERMEDIATE_KEYWORDS.get(rule_name, [])
    evidence_lower = evidence.lower()
    return any(kw.lower() in evidence_lower for kw in keywords)


def _generate_hypotheses_cc(
    db_context: str,
    semantic_context: str,
    metrics_context: str,
    ontology_context: str,
) -> list[Hypothesis]:
    """Generate chain hypotheses using Claude Code CLI."""
    system = SYSTEM_PROMPT.format(
        db_context=db_context,
        semantic_context=semantic_context,
        metrics_context=metrics_context,
        ontology_context=ontology_context,
    )
    text = call_claude_code(CHAIN_HYPOTHESIS_GENERATION_PROMPT, system=system)
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


def run_chain_comparison(
    num_trials: int = 3,
) -> dict[ChainCondition, ChainConditionSummary]:
    """Run RDF vs NL vs MEMO vs DOC comparison for multi-hop causal reasoning.

    For each condition and trial:
    1. Generate hypotheses via Claude Code
    2. Execute SQL and verify via Claude Code
    3. Compare LLM verdict to demo ground truth
    4. Check if LLM mentions intermediate causal steps
    """
    console.print("[bold]Multi-Hop Causal Chain Comparison (RDF/NL/MEMO/DOC)[/]")
    console.print(f"Trials per condition: {num_trials}\n")

    console.print("[blue]Assembling shared context...[/]")
    db_context, semantic_context, metrics_context = _assemble_shared_context()

    ontology_contexts = _build_ontology_contexts()

    console.print("[blue]Computing chain ground truth...[/]")
    ground_truth = _get_chain_ground_truth()
    demo_rules = list(ground_truth.keys())
    console.print(f"  Ground truth: {ground_truth}\n")

    summaries: dict[ChainCondition, ChainConditionSummary] = {}

    for condition in ChainCondition:
        console.print(f"[bold blue]Condition: {condition.value.upper()}[/]")
        summary = ChainConditionSummary(condition=condition, num_trials=num_trials)
        ontology_context = ontology_contexts[condition]

        conn = get_connection()

        for trial_id in range(1, num_trials + 1):
            console.print(f"\n  [dim]Trial {trial_id}/{num_trials}[/]")

            try:
                hypotheses = _generate_hypotheses_cc(
                    db_context, semantic_context, metrics_context, ontology_context,
                )
            except Exception as e:
                console.print(f"    [red]Generation failed: {e}[/]")
                continue

            matched_rules: set[str] = set()

            for h in hypotheses:
                matched = _match_chain_rule(h.ontology_rule, demo_rules)
                if not matched or matched in matched_rules:
                    continue
                matched_rules.add(matched)

                query_result = execute_query(conn, h.sql_query)
                if query_result and "error" in query_result[0]:
                    console.print(
                        f"    [red]SQL error for {matched}: "
                        f"{query_result[0]['error'][:60]}[/]"
                    )
                    continue

                try:
                    result = _verify_hypothesis_cc(h, query_result)
                except Exception as e:
                    console.print(f"    [red]Verification failed for {matched}: {e}[/]")
                    continue

                expected = ground_truth[matched]
                mentions_intermediate = _check_intermediate_mention(
                    matched, result.evidence_summary,
                )

                trial = ChainTrialResult(
                    condition=condition,
                    trial_id=trial_id,
                    rule_name=matched,
                    expected_verdict=expected,
                    llm_verdict=result.verdict,
                    llm_evidence=result.evidence_summary,
                    is_correct=(result.verdict == expected),
                    mentions_intermediate=mentions_intermediate,
                )
                summary.trials.append(trial)

                mark = "[green]OK[/]" if trial.is_correct else "[red]NG[/]"
                chain_mark = "[cyan]CHAIN[/]" if mentions_intermediate else "[dim]FLAT[/]"
                console.print(
                    f"    {mark} {chain_mark} {matched[:50]}: "
                    f"LLM={result.verdict} vs GT={expected}"
                )

        conn.close()
        summaries[condition] = summary
        console.print(f"\n  [bold]Accuracy: {summary.accuracy:.1%}[/]")
        console.print(f"  [bold]Chain awareness: {summary.chain_awareness:.1%}[/]")

    from ontoprobe.evaluation.chain_comparison_report import (
        generate_chain_comparison_report,
    )

    generate_chain_comparison_report(summaries, ground_truth)

    return summaries
