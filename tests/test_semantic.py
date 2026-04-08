from ontoprobe.semantic.manifest import load_manifest, format_manifest_context
from ontoprobe.semantic.metrics import load_metrics, format_metrics_context


def test_load_manifest():
    models = load_manifest()
    assert len(models) > 0
    model_names = {m.name for m in models}
    assert "fct_orders" in model_names


def test_manifest_columns():
    models = load_manifest()
    fct_orders = next(m for m in models if m.name == "fct_orders")
    col_names = {c.name for c in fct_orders.columns}
    assert "total_amount" in col_names


def test_load_metrics():
    metrics = load_metrics()
    assert len(metrics) >= 5
    metric_names = {m.name for m in metrics}
    assert "total_revenue" in metric_names
    assert "order_count" in metric_names


def test_format_metrics_context():
    metrics = load_metrics()
    context = format_metrics_context(metrics)
    assert "## Available Metrics" in context
    assert "total_revenue" in context
