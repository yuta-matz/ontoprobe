"""Parse dbt manifest.json to extract model and column metadata."""

import json
from dataclasses import dataclass

from ontoprobe.config import DBT_MANIFEST_PATH


@dataclass
class ColumnMeta:
    name: str
    description: str


@dataclass
class ModelMeta:
    name: str
    description: str
    columns: list[ColumnMeta]


def load_manifest(path: str | None = None) -> list[ModelMeta]:
    """Load dbt manifest.json and extract model metadata."""
    manifest_path = path or DBT_MANIFEST_PATH
    with open(manifest_path) as f:
        manifest = json.load(f)

    models = []
    for key, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") != "model":
            continue

        columns = [
            ColumnMeta(name=col_name, description=col_data.get("description", ""))
            for col_name, col_data in node.get("columns", {}).items()
        ]

        models.append(ModelMeta(
            name=node["name"],
            description=node.get("description", ""),
            columns=columns,
        ))
    return models


def format_manifest_context(models: list[ModelMeta]) -> str:
    """Format dbt model metadata as text for LLM context."""
    lines = ["## Semantic Layer (dbt Models)\n"]
    for model in models:
        lines.append(f"### {model.name}")
        if model.description:
            lines.append(f"  {model.description}")
        for col in model.columns:
            desc = f": {col.description}" if col.description else ""
            lines.append(f"  - {col.name}{desc}")
        lines.append("")
    return "\n".join(lines)
