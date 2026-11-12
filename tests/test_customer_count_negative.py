"""Regression tests: SQL may execute but count the wrong entity."""
from text_to_sql.validation import validate_answer

QUESTION = "How many customers are in each region?"
COLUMNS = ["region", "customer_count"]
ROWS = [["East", 10]]


def check(sql):
    return validate_answer(QUESTION, sql, COLUMNS, ROWS)


def test_plain_customer_count_is_valid():
    report = check("SELECT region, COUNT(*) FROM customers GROUP BY region")
    assert report.status == "pass"


def test_joined_row_count_is_flagged():
    report = check("""SELECT c.region, COUNT(*) AS customer_count
        FROM customers c JOIN orders o ON c.customer_id = o.customer_id
        GROUP BY c.region""")
    assert report.status == "warning"
    assert "customer_count_semantics" in [n for n, ok, _ in report.checks if ok is False]


def test_joined_order_count_is_flagged():
    report = check("""SELECT c.region, COUNT(o.order_id) AS customer_count
        FROM customers c JOIN orders o ON c.customer_id = o.customer_id
        GROUP BY c.region""")
    assert report.status == "warning"


def test_distinct_customer_id_after_join_is_accepted():
    report = check("""SELECT c.region, COUNT(DISTINCT c.customer_id) AS customer_count
        FROM customers c JOIN orders o ON c.customer_id = o.customer_id
        GROUP BY c.region""")
    assert report.status == "pass"


def test_distinct_order_id_after_join_is_flagged():
    report = check("""SELECT c.region, COUNT(DISTINCT o.order_id) AS customer_count
        FROM customers c JOIN orders o ON c.customer_id = o.customer_id
        GROUP BY c.region""")
    assert report.status == "warning"
