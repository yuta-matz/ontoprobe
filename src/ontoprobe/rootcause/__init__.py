"""Section 5.4 root-cause loop verification.

An agent-loop experiment distinct from the flat hypothesis-batch testing
in src/ontoprobe/hypotheses/: the LLM is primed with a detected anomaly
and must traverse the ontology's causal chain backward, querying the
semantic layer along the way, until it reports a root cause. Ground
truth is injected per round via data_gen so downstream evaluation can
measure hit rate, traversal depth, and branch precision.
"""
