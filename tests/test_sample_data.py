from pathlib import Path

import duckdb

from text_to_sql.sample_data import build_database
from text_to_sql.schema import get_schema, ALLOWED_TABLES


def test_expected_tables_and_columns(tmp_path: Path):
    path = build_database(tmp_path / 'sales.duckdb')
    schema = get_schema(path)
    assert set(schema) == ALLOWED_TABLES
    assert {'order_id', 'customer_id', 'order_date', 'status'} <= {
        col['name'] for col in schema['orders']
    }
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute('SELECT COUNT(*) FROM orders').fetchone()[0] == 240
        assert con.execute('SELECT COUNT(*) FROM customers').fetchone()[0] == 40
        assert con.execute('SELECT COUNT(*) FROM products').fetchone()[0] == 16


def test_rebuild_is_deterministic(tmp_path: Path):
    path = tmp_path / 'sales.duckdb'
    build_database(path)
    with duckdb.connect(str(path), read_only=True) as con:
        first = con.execute('SELECT SUM(quantity * unit_price) FROM order_items').fetchone()[0]
    build_database(path)
    with duckdb.connect(str(path), read_only=True) as con:
        second = con.execute('SELECT SUM(quantity * unit_price) FROM order_items').fetchone()[0]
    assert first == second


def test_referential_integrity(tmp_path: Path):
    path = build_database(tmp_path / 'sales.duckdb')
    with duckdb.connect(str(path), read_only=True) as con:
        orphan_items = con.execute('''
            SELECT COUNT(*) FROM order_items i
            LEFT JOIN orders o ON i.order_id = o.order_id
            WHERE o.order_id IS NULL
        ''').fetchone()[0]
        assert orphan_items == 0
