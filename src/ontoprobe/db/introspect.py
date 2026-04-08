"""Extract schema metadata from DuckDB for LLM context."""

from dataclasses import dataclass

import duckdb


@dataclass
class ColumnInfo:
    name: str
    data_type: str
    is_nullable: bool


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    row_count: int


def get_tables(conn: duckdb.DuckDBPyConnection) -> list[TableInfo]:
    """Get metadata for all tables in the database."""
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
    ).fetchall()

    result = []
    for (table_name,) in tables:
        columns = conn.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'main' AND table_name = ?",
            [table_name],
        ).fetchall()

        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

        result.append(TableInfo(
            name=table_name,
            columns=[
                ColumnInfo(name=c[0], data_type=c[1], is_nullable=c[2] == "YES")
                for c in columns
            ],
            row_count=row_count,
        ))
    return result


def format_schema_context(tables: list[TableInfo]) -> str:
    """Format table metadata as text for LLM context."""
    lines = ["## Database Schema\n"]
    for table in tables:
        lines.append(f"### {table.name} ({table.row_count:,} rows)")
        for col in table.columns:
            nullable = ", nullable" if col.is_nullable else ""
            lines.append(f"  - {col.name}: {col.data_type}{nullable}")
        lines.append("")
    return "\n".join(lines)
