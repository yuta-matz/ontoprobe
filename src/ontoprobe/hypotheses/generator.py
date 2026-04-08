"""LLM-based hypothesis generation."""

import json

import anthropic

from ontoprobe.hypotheses.models import Hypothesis
from ontoprobe.hypotheses.templates import HYPOTHESIS_GENERATION_PROMPT, SYSTEM_PROMPT


def generate_hypotheses(
    db_context: str,
    semantic_context: str,
    metrics_context: str,
    ontology_context: str,
) -> list[Hypothesis]:
    """Generate hypotheses using the LLM based on all three context layers."""
    client = anthropic.Anthropic()

    system = SYSTEM_PROMPT.format(
        db_context=db_context,
        semantic_context=semantic_context,
        metrics_context=metrics_context,
        ontology_context=ontology_context,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": HYPOTHESIS_GENERATION_PROMPT}],
    )

    text = response.content[0].text
    # Extract JSON from response (handle potential markdown code blocks)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    data = json.loads(text)
    return [Hypothesis(**h) for h in data["hypotheses"]]
