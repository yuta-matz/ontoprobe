"""Run the ontology effectiveness evaluation and generate report."""

from ontoprobe.evaluation.levels import LEVEL_NAMES, format_level_context
from ontoprobe.evaluation.report import generate_report
from ontoprobe.evaluation.scorer import get_marginal_contribution, get_scores_by_level
from ontoprobe.ontology.loader import load_ontology
from ontoprobe.ontology.query import get_causal_rules, get_metric_mappings


def run_evaluation() -> None:
    """Run full evaluation and generate report."""
    # Load ontology data
    graph = load_ontology()
    rules = get_causal_rules(graph)
    mappings = get_metric_mappings(graph)

    # Generate context for each level (for inclusion in report)
    level_contexts = {}
    for level in range(6):
        level_contexts[level] = format_level_context(level, rules, mappings)

    # Get scores and marginal contributions
    summaries = get_scores_by_level()
    contributions = get_marginal_contribution()

    # Generate report
    generate_report(summaries, contributions, level_contexts, LEVEL_NAMES)


if __name__ == "__main__":
    run_evaluation()
