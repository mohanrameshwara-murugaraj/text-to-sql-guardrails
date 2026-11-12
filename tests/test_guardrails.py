import pytest
from text_to_sql.guardrails import GuardrailPolicy, UnsafeQuery, validate_sql

POLICY = GuardrailPolicy(allowed_tables=frozenset({"orders"}), max_rows=100)


@pytest.mark.parametrize("sql", [
    "DELETE FROM orders",
    "DROP TABLE orders",
    "UPDATE orders SET amount=0",
    "INSERT INTO orders VALUES (1)",
    "SELECT * FROM orders; DROP TABLE orders",
    "SELECT * FROM secret_table",
    "SELECT * FROM read_csv('/tmp/secret.csv')",
    "SELECT * FROM orders JOIN secret_table USING (id)",
    "WITH x AS (SELECT * FROM orders) SELECT * FROM x",
    "SELECT (SELECT 1) FROM orders",
    "SELECT current_setting('x') FROM orders",
    "SELECT * FROM main.orders",
    "SELECT * FROM orders LIMIT -1",
    "SELECT * FROM orders LIMIT 0",
])
def test_rejected(sql):
    with pytest.raises(UnsafeQuery):
        validate_sql(sql, POLICY)


def test_safe_query_is_capped():
    sql = validate_sql("SELECT id FROM orders WHERE amount > 20", POLICY)
    assert sql == "SELECT id FROM orders WHERE amount > 20 LIMIT 100"


def test_existing_limit_is_reduced():
    sql = validate_sql("SELECT * FROM orders LIMIT 500", POLICY)
    assert sql.endswith("LIMIT 100")


def test_smaller_limit_is_preserved():
    sql = validate_sql("SELECT * FROM orders LIMIT 5", POLICY)
    assert sql.endswith("LIMIT 5")
