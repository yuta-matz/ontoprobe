from ontoprobe.db.introspect import get_tables, format_schema_context


def test_get_tables(conn):
    tables = get_tables(conn)
    table_names = {t.name for t in tables}
    assert "orders" in table_names
    assert "customers" in table_names
    assert "products" in table_names


def test_tables_have_rows(conn):
    tables = get_tables(conn)
    orders = next(t for t in tables if t.name == "orders")
    assert orders.row_count > 0


def test_format_schema_context(conn):
    tables = get_tables(conn)
    context = format_schema_context(tables)
    assert "## Database Schema" in context
    assert "orders" in context
