"""Load OWL/TTL ontology files into an RDF graph."""

from pathlib import Path

from rdflib import Graph

from ontoprobe.config import ONTOLOGY_DIR


def load_ontology(
    directory: Path | None = None, variant: str | None = None
) -> Graph:
    """Load all .ttl files from the ontology directory into a single graph.

    When ``variant`` is set (e.g. ``"inverted"``), loads from
    ``ontology_{variant}/`` at the project root instead of the default
    ``ontology/`` directory. Used by Phase 10 to swap in a
    prior-contradicting causal ruleset.
    """
    if directory is not None:
        ont_dir = directory
    elif variant:
        ont_dir = ONTOLOGY_DIR.parent / f"ontology_{variant}"
    else:
        ont_dir = ONTOLOGY_DIR
    graph = Graph()
    for ttl_file in sorted(ont_dir.glob("*.ttl")):
        graph.parse(str(ttl_file), format="turtle")
    return graph
