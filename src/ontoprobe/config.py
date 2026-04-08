from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
SEED_DIR = DATA_DIR / "seed"
ONTOLOGY_DIR = ROOT_DIR / "ontology"
DBT_PROJECT_DIR = ROOT_DIR / "dbt_project"
DBT_MANIFEST_PATH = DBT_PROJECT_DIR / "target" / "manifest.json"

DUCKDB_PATH = DATA_DIR / "ontoprobe.duckdb"
