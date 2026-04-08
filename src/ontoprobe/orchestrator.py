"""Main pipeline: assemble context → generate hypotheses → verify → report."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ontoprobe.db.connection import get_connection
from ontoprobe.db.introspect import format_schema_context, get_tables
from ontoprobe.hypotheses.demo import DEMO_HYPOTHESES, verify_demo
from ontoprobe.hypotheses.generator import generate_hypotheses
from ontoprobe.hypotheses.models import VerificationResult
from ontoprobe.hypotheses.verifier import execute_query, verify_hypothesis
from ontoprobe.ontology.loader import load_ontology
from ontoprobe.ontology.query import (
    format_ontology_context,
    get_causal_rules,
    get_metric_mappings,
)
from ontoprobe.semantic.manifest import format_manifest_context, load_manifest
from ontoprobe.semantic.metrics import format_metrics_context, load_metrics

console = Console()


def assemble_context() -> tuple[str, str, str, str]:
    """Assemble context from all three layers."""
    console.print("[bold blue]Assembling context from 3 layers...[/]")

    # Layer 1: DB Metadata
    conn = get_connection()
    tables = get_tables(conn)
    db_context = format_schema_context(tables)
    conn.close()
    console.print(f"  DB Metadata: {len(tables)} tables")

    # Layer 2: Semantic Layer
    models = load_manifest()
    metrics = load_metrics()
    semantic_context = format_manifest_context(models)
    metrics_context = format_metrics_context(metrics)
    console.print(f"  Semantic Layer: {len(models)} models, {len(metrics)} metrics")

    # Layer 3: Ontology
    graph = load_ontology()
    rules = get_causal_rules(graph)
    mappings = get_metric_mappings(graph)
    ontology_context = format_ontology_context(rules, mappings)
    console.print(f"  Ontology: {len(rules)} causal rules, {len(mappings)} metric mappings")

    return db_context, semantic_context, metrics_context, ontology_context


def run_pipeline(demo: bool = False) -> list[VerificationResult]:
    """Run the full hypothesis testing pipeline."""
    mode = "Demo Mode (no LLM)" if demo else "LLM-Powered"
    console.print(Panel(f"[bold]OntoProbe: {mode} Hypothesis Testing[/]", expand=False))

    # Step 1: Assemble context
    db_context, semantic_context, metrics_context, ontology_context = assemble_context()

    # Step 2: Generate hypotheses
    if demo:
        console.print("\n[bold blue]Loading demo hypotheses...[/]")
        hypotheses = DEMO_HYPOTHESES
    else:
        console.print("\n[bold blue]Generating hypotheses via LLM...[/]")
        hypotheses = generate_hypotheses(db_context, semantic_context, metrics_context, ontology_context)
    console.print(f"  Generated {len(hypotheses)} hypotheses")

    for i, h in enumerate(hypotheses, 1):
        console.print(f"\n  [bold]{i}. {h.description}[/]")
        console.print(f"     Rule: {h.ontology_rule}")
        console.print(f"     Expected: {h.expected_direction}")

    # Step 3: Execute and verify
    console.print("\n[bold blue]Verifying hypotheses against data...[/]")
    conn = get_connection()
    results = []

    for i, hypothesis in enumerate(hypotheses, 1):
        console.print(f"\n  [{i}/{len(hypotheses)}] Testing: {hypothesis.description}")

        # Execute SQL
        query_result = execute_query(conn, hypothesis.sql_query)
        if query_result and "error" in query_result[0]:
            console.print(f"    [red]SQL Error: {query_result[0]['error']}[/]")
            results.append(VerificationResult(
                hypothesis=hypothesis,
                query_result=query_result,
                verdict="inconclusive",
                evidence_summary=f"SQL execution failed: {query_result[0]['error']}",
            ))
            continue

        # Verify
        if demo:
            result = verify_demo(hypothesis, query_result)
        else:
            result = verify_hypothesis(hypothesis, query_result)
        results.append(result)

        color = {"supported": "green", "contradicted": "red", "inconclusive": "yellow"}
        console.print(f"    Verdict: [{color.get(result.verdict, 'white')}]{result.verdict}[/]")
        console.print(f"    Evidence: {result.evidence_summary}")

    conn.close()

    # Step 4: Summary
    print_summary(results)
    return results


def print_summary(results: list[VerificationResult]) -> None:
    """Print a summary table of all results."""
    table = Table(title="\nHypothesis Testing Results")
    table.add_column("#", style="dim", width=3)
    table.add_column("Hypothesis", max_width=50)
    table.add_column("Rule", max_width=30)
    table.add_column("Verdict", justify="center")
    table.add_column("Evidence", max_width=40)

    for i, r in enumerate(results, 1):
        color = {"supported": "green", "contradicted": "red", "inconclusive": "yellow"}
        verdict_style = color.get(r.verdict, "white")
        table.add_row(
            str(i),
            r.hypothesis.description[:50],
            r.hypothesis.ontology_rule[:30],
            f"[{verdict_style}]{r.verdict}[/]",
            r.evidence_summary[:40],
        )

    console.print(table)

    supported = sum(1 for r in results if r.verdict == "supported")
    contradicted = sum(1 for r in results if r.verdict == "contradicted")
    inconclusive = sum(1 for r in results if r.verdict == "inconclusive")
    console.print(
        f"\n[bold]Summary:[/] {supported} supported, "
        f"{contradicted} contradicted, {inconclusive} inconclusive "
        f"(out of {len(results)} hypotheses)"
    )
