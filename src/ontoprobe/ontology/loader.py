"""Load OWL/TTL ontology files into an RDF graph."""

from pathlib import Path

from rdflib import Graph

from ontoprobe.config import ONTOLOGY_DIR


def load_ontology(directory: Path | None = None) -> Graph:
    """Load all .ttl files from the ontology directory into a single graph."""
    ont_dir = directory or ONTOLOGY_DIR
    graph = Graph()
    for ttl_file in sorted(ont_dir.glob("*.ttl")):
        graph.parse(str(ttl_file), format="turtle")
    return graph
