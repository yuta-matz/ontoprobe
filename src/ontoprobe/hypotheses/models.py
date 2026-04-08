"""Pydantic models for hypothesis generation and verification."""

from pydantic import BaseModel


class Hypothesis(BaseModel):
    """A testable hypothesis derived from domain knowledge."""

    description: str
    ontology_rule: str
    expected_direction: str
    sql_query: str
    relevant_metrics: list[str]
    relevant_dimensions: list[str]


class VerificationResult(BaseModel):
    """Result of testing a hypothesis against data."""

    hypothesis: Hypothesis
    query_result: list[dict]
    verdict: str  # "supported", "contradicted", "inconclusive"
    evidence_summary: str
