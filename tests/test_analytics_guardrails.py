import pytest
from text_to_sql.guardrails import GuardrailPolicy, UnsafeQuery, validate_sql

POLICY = GuardrailPolicy(frozenset({"customers", "orders", "order_items", "products", "refunds"}), 100)

QUERY = """
SELECT c.region, COUNT(DISTINCT o.order_id) AS total_orders,
       ROUND(SUM(oi.quantity * oi.unit_price), 2) AS gross_sales
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'completed'
GROUP BY c.region
ORDER BY gross_sales DESC
"""


def test_business_analytics_allowed():
    assert validate_sql(QUERY, POLICY).endswith("LIMIT 100")


def test_left_join_allowed():
    sql = "SELECT c.region, COUNT(o.order_id) FROM customers c LEFT JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.region"
    assert validate_sql(sql, POLICY).endswith("LIMIT 100")


@pytest.mark.parametrize("sql", [
    "SELECT * FROM orders CROSS JOIN customers",
    "SELECT * FROM orders o JOIN customers c ON TRUE",
    "SELECT * FROM orders o JOIN customers c ON o.customer_id > c.customer_id",
    "SELECT * FROM orders o JOIN secrets s ON o.customer_id = s.id",
    "SELECT read_csv('/tmp/secrets.csv') FROM orders",
    "SELECT * FROM orders; DELETE FROM orders",
    "SELECT (SELECT 1) FROM orders",
    "SELECT * FROM orders o JOIN customers c USING (customer_id)",
    "SELECT * FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE customer_id = 1",
])
def test_unsafe_or_unsupported_analytics_rejected(sql):
    with pytest.raises(UnsafeQuery):
        validate_sql(sql, POLICY)
