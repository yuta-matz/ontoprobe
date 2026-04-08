"""Prompt templates for LLM-based hypothesis generation and verification."""

SYSTEM_PROMPT = """\
You are a data analyst with deep domain expertise in e-commerce.
You have access to a database with the following schema, semantic layer, and domain knowledge.

{db_context}

{semantic_context}

{metrics_context}

{ontology_context}

Use this knowledge to generate and test hypotheses about the e-commerce data.
All SQL must be valid DuckDB SQL and query the available tables/views directly.
"""

HYPOTHESIS_GENERATION_PROMPT = """\
Based on the domain knowledge (causal rules) provided, generate testable hypotheses.

For each hypothesis:
1. Identify which causal rule it derives from
2. Write a specific, testable claim
3. Write the DuckDB SQL query that would test this hypothesis
4. Identify the expected direction of the result

Return your response as a JSON array of objects with this schema:
{{
  "hypotheses": [
    {{
      "description": "Specific testable claim",
      "ontology_rule": "Name of the causal rule this derives from",
      "expected_direction": "increase/decrease/correlation",
      "sql_query": "SELECT ... FROM ...",
      "relevant_metrics": ["metric_name"],
      "relevant_dimensions": ["dimension_name"]
    }}
  ]
}}

Generate one hypothesis per causal rule. Make each SQL query self-contained and executable.
Return ONLY the JSON, no other text.
"""

VERIFICATION_PROMPT = """\
Analyze the following query result for this hypothesis:

**Hypothesis:** {description}
**Expected:** {expected_direction}
**Ontology Rule:** {ontology_rule}

**Query Result:**
{query_result}

Determine whether the data supports, contradicts, or is inconclusive for this hypothesis.
Provide a brief evidence summary explaining your reasoning.

Return your response as JSON:
{{
  "verdict": "supported" | "contradicted" | "inconclusive",
  "evidence_summary": "Brief explanation of the evidence"
}}

Return ONLY the JSON, no other text.
"""
