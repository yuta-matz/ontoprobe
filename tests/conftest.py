import pytest
import duckdb

from ontoprobe.db.seeder import generate_seed_data, load_seed_to_duckdb
from ontoprobe.config import SEED_DIR, DUCKDB_PATH


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    """Ensure seed data and DuckDB are ready for tests."""
    if not list(SEED_DIR.glob("*.csv")):
        generate_seed_data()
    if not DUCKDB_PATH.exists():
        load_seed_to_duckdb()


@pytest.fixture
def conn():
    """Provide a DuckDB connection for tests."""
    connection = duckdb.connect(str(DUCKDB_PATH))
    yield connection
    connection.close()
