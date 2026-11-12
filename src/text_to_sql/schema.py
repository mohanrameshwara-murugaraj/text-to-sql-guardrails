"""Read metadata from the synthetic DuckDB database (never user-generated SQL)."""
from __future__ import annotations
from pathlib import Path
import duckdb


ALLOWED_TABLES = frozenset({"customers", "products", "orders", "order_items", "refunds"})


def get_schema(path: str | Path) -> dict[str, list[dict[str, object]]]:
    """Read allowed tables and columns from DuckDB information_schema."""
    with duckdb.connect(str(path), read_only=True) as con:
        columns = con.execute("""
            SELECT table_name, column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = 'main'
            ORDER BY table_name, ordinal_position
        """).fetchall()
    result: dict[str, list[dict[str, object]]] = {}
    for table, column, dtype, nullable, _ in columns:
        if table in ALLOWED_TABLES:
            result.setdefault(table, []).append({
                "name": column, "type": dtype, "nullable": nullable == "YES"
            })
    return result
