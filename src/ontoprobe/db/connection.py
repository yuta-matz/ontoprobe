import duckdb

from ontoprobe.config import DUCKDB_PATH


def get_connection(path: str | None = None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path or DUCKDB_PATH))
