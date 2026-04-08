from ontoprobe.ontology.loader import load_ontology
from ontoprobe.ontology.query import get_causal_rules, get_metric_mappings, format_ontology_context


def test_load_ontology():
    graph = load_ontology()
    assert len(graph) > 0


def test_causal_rules():
    graph = load_ontology()
    rules = get_causal_rules(graph)
    assert len(rules) >= 5
    rule_labels = [r.label for r in rules]
    assert any("VIP" in label for label in rule_labels)
    assert any("Seasonal" in label or "Q4" in label for label in rule_labels)


def test_metric_mappings():
    graph = load_ontology()
    mappings = get_metric_mappings(graph)
    assert len(mappings) >= 5
    dbt_names = {m.dbt_metric for m in mappings}
    assert "total_revenue" in dbt_names
    assert "order_count" in dbt_names


def test_format_ontology_context():
    graph = load_ontology()
    rules = get_causal_rules(graph)
    mappings = get_metric_mappings(graph)
    context = format_ontology_context(rules, mappings)
    assert "## Domain Knowledge" in context
    assert "Causal Rules" in context
