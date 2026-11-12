"""Integration coverage: policy + read-only DuckDB + result serialization."""
from pathlib import Path

import duckdb
import pytest

from text_to_sql.executor import execute_query
from text_to_sql.guardrails import GuardrailPolicy, UnsafeQuery
from text_to_sql.sample_data import build_database


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("executor") / "sales.duckdb"
    build_database(path)
    return path


@pytest.fixture
def policy():
    return GuardrailPolicy(
        allowed_tables=frozenset({"customers", "orders", "order_items", "products", "refunds"}),
        max_rows=100,
    )


def test_aggregated_join_matches_reference_values(db, policy):
    sql = """
        SELECT c.region, COUNT(DISTINCT o.order_id) AS total_orders,
               ROUND(SUM(oi.quantity * oi.unit_price), 2) AS gross_sales
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN order_items oi ON o.order_id = oi.order_id
        WHERE o.status = 'completed'
        GROUP BY c.region
        ORDER BY gross_sales DESC
    """
    result = execute_query(sql, db, policy)
    assert result.columns == ["region", "total_orders", "gross_sales"]
    assert [row[0] for row in result.rows] == ["South", "North", "West", "East"]
    assert [row[1] for row in result.rows] == [56, 58, 59, 53]
    assert [float(row[2]) for row in result.rows] == [44041.0, 40721.0, 40181.5, 36744.0]
    assert result.row_count == 4
    assert result.execution_ms >= 0


def test_limit_capped(db, policy):
    result = execute_query("SELECT customer_id FROM customers LIMIT 9999", db,
                           GuardrailPolicy(policy.allowed_tables, max_rows=7))
    assert result.row_count == 7
    assert "LIMIT 7" in result.sql.upper()


@pytest.mark.parametrize("sql", [
    "DELETE FROM customers",
    "DROP TABLE customers",
    "SELECT * FROM secret_table",
    "SELECT * FROM customers; DELETE FROM customers",
    "SELECT read_csv('/etc/passwd')",
])
def test_rejected_before_execution(db, policy, sql):
    with pytest.raises(UnsafeQuery):
        execute_query(sql, db, policy)


def test_missing_database_rejected(policy, tmp_path):
    with pytest.raises(FileNotFoundError):
        execute_query("SELECT * FROM customers", tmp_path / "missing.duckdb", policy)


def test_query_cannot_mutate_database(db, policy):
    with duckdb.connect(str(db), read_only=True) as con:
        before = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    with pytest.raises(UnsafeQuery):
        execute_query("UPDATE customers SET region = 'BAD'", db, policy)
    with duckdb.connect(str(db), read_only=True) as con:
        after = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    assert before == after == 40


def test_json_shape(db, policy):
    result = execute_query("SELECT customer_id, region FROM customers LIMIT 1", db, policy)
    payload = result.to_dict()
    assert payload["row_count"] == 1
    assert payload["columns"] == ["customer_id", "region"]
    assert isinstance(payload["rows"], list)
