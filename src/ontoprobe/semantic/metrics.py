"""Parse metrics definition YAML for LLM context."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ontoprobe.config import DATA_DIR

METRICS_PATH = DATA_DIR / "metrics.yml"


@dataclass
class MetricDef:
    name: str
    label: str
    description: str
    model: str
    expression: str
    dimensions: list[str] = field(default_factory=list)
    timestamp_column: str | None = None
    time_grains: list[str] = field(default_factory=list)


def load_metrics(path: str | Path | None = None) -> list[MetricDef]:
    """Load metrics from YAML file."""
    metrics_path = Path(path) if path else METRICS_PATH
    with open(metrics_path) as f:
        data = yaml.safe_load(f)

    return [
        MetricDef(
            name=m["name"],
            label=m["label"],
            description=m["description"],
            model=m["model"],
            expression=m["expression"],
            dimensions=m.get("dimensions", []),
            timestamp_column=m.get("timestamp_column"),
            time_grains=m.get("time_grains", []),
        )
        for m in data.get("metrics", [])
    ]


def format_metrics_context(metrics: list[MetricDef]) -> str:
    """Format metrics as text for LLM context."""
    lines = ["## Available Metrics\n"]
    for m in metrics:
        lines.append(f"### {m.label} (`{m.name}`)")
        lines.append(f"  {m.description}")
        lines.append(f"  Expression: `{m.expression}` on `{m.model}`")
        if m.dimensions:
            lines.append(f"  Dimensions: {', '.join(m.dimensions)}")
        if m.time_grains:
            lines.append(f"  Time grains: {', '.join(m.time_grains)}")
        lines.append("")
    return "\n".join(lines)
