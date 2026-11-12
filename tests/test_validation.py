from text_to_sql.validation import validate_answer
from text_to_sql.llm import SQLCandidate
from text_to_sql.pipeline import ask_database
from text_to_sql.sample_data import build_database


def validate(question, sql):
    return validate_answer(question, sql, ['region', 'value'], [['East', 10]])


def test_correct_customer_counts_pass():
    r = validate('How many customers are in each region?', 'SELECT region, COUNT(*) FROM customers GROUP BY region')
    assert r.status == 'pass'
    assert r.score == 100


def test_wrong_grouping_is_flagged():
    r = validate('How many customers are in each region?', 'SELECT COUNT(*) FROM customers')
    assert r.status == 'warning'
    assert 'region_group' in [name for name, ok, _ in r.checks if ok is False]


def test_wrong_table_is_flagged():
    r = validate('How many customers are in each region?', 'SELECT region, COUNT(*) FROM orders GROUP BY region')
    assert r.status == 'warning'


def test_gross_sales_without_completed_filter_is_flagged():
    sql = 'SELECT c.region, SUM(oi.quantity * oi.unit_price) FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id GROUP BY c.region'
    r = validate('Gross sales by region', sql)
    assert r.status == 'warning'
    assert 'completed_only' in [name for name, ok, _ in r.checks if ok is False]


def test_gross_sales_correct_formula_passes():
    sql = "SELECT c.region, SUM(oi.quantity * oi.unit_price) FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id WHERE o.status = 'completed' GROUP BY c.region"
    assert validate('Gross sales by region', sql).status == 'pass'


def test_unknown_intent_abstains():
    r = validate('Which customers are most loyal?', 'SELECT customer_id FROM customers')
    assert r.status == 'unverified'


def test_empty_result_is_inconclusive():
    r = validate_answer('How many customers are in each region?', 'SELECT region, COUNT(*) FROM customers GROUP BY region', ['region', 'count'], [])
    assert r.status == 'unverified'


def test_pipeline_attaches_report(tmp_path):
    db = tmp_path / 'sales.duckdb'
    build_database(db)
    candidate = SQLCandidate('SELECT region, COUNT(*) FROM customers GROUP BY region ORDER BY region', 'counts', ('customers',))
    result = ask_database('How many customers are in each region?', db, generator=lambda _: candidate)
    assert result.status == 'executed'
    assert result.validation is not None
    assert result.validation.status == 'pass'
