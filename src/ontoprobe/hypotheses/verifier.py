"""Execute SQL queries and verify hypotheses against data."""

import json

import anthropic
import duckdb

from ontoprobe.hypotheses.models import Hypothesis, VerificationResult
from ontoprobe.hypotheses.templates import VERIFICATION_PROMPT


def execute_query(conn: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    """Execute a SQL query and return results as list of dicts."""
    try:
        result = conn.execute(sql)
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    except Exception as e:
        return [{"error": str(e)}]


def verify_hypothesis(
    hypothesis: Hypothesis,
    query_result: list[dict],
) -> VerificationResult:
    """Use LLM to analyze query results and determine verdict."""
    client = anthropic.Anthropic()

    # Format query result for display
    result_text = json.dumps(query_result, indent=2, default=str)
    if len(result_text) > 3000:
        result_text = result_text[:3000] + "\n... (truncated)"

    prompt = VERIFICATION_PROMPT.format(
        description=hypothesis.description,
        expected_direction=hypothesis.expected_direction,
        ontology_rule=hypothesis.ontology_rule,
        query_result=result_text,
    )

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    data = json.loads(text)

    return VerificationResult(
        hypothesis=hypothesis,
        query_result=query_result,
        verdict=data["verdict"],
        evidence_summary=data["evidence_summary"],
    )
