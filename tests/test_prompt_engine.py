"""No network, no LLM and no database required for these deterministic tests."""
from text_to_sql.prompt_engine import build_prompt, detect_ambiguity, select_tables

SCHEMA = {
    "customers": [
        {"name": "customer_id", "type": "INTEGER"},
        {"name": "region", "type": "VARCHAR"},
    ],
    "orders": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "customer_id", "type": "INTEGER"},
        {"name": "status", "type": "VARCHAR"},
    ],
    "order_items": [
        {"name": "order_id", "type": "INTEGER"},
        {"name": "quantity", "type": "INTEGER"},
        {"name": "unit_price", "type": "DECIMAL"},
    ],
    "products": [{"name": "product_id", "type": "INTEGER"}],
    "refunds": [{"name": "refund_id", "type": "INTEGER"}],
}


def test_customer_question_only_includes_customer_schema():
    result = build_prompt("How many customers per region?", SCHEMA)
    assert result.selected_tables == ("customers",)
    assert "customers: customer_id" in result.prompt
    assert "order_items:" not in result.prompt


def test_gross_sales_includes_orders_bridge():
    result = build_prompt("Gross sales by region", SCHEMA)
    assert set(result.selected_tables) == {"customers", "orders", "order_items"}
    assert "orders.customer_id = customers.customer_id" in result.prompt


def test_revenue_requires_clarification():
    result = build_prompt("Show revenue by region", SCHEMA)
    assert result.prompt is None
    assert result.clarification is not None
    assert len(result.clarification.options) == 2


def test_explicit_gross_and_net_not_ambiguous():
    assert detect_ambiguity("Gross revenue by region") is None
    assert detect_ambiguity("Net revenue by region") is None


def test_refund_rate_clarified():
    result = build_prompt("Show refund rate", SCHEMA)
    assert result.clarification is not None
    assert "denominators" in result.clarification.reason


def test_unknown_question_fail_closed():
    result = build_prompt("How many employees are on payroll?", SCHEMA)
    assert result.prompt is None
    assert result.clarification is not None


def test_empty_question_rejected():
    import pytest
    with pytest.raises(ValueError):
        build_prompt("  ", SCHEMA)


def test_input_schema_controls_selection():
    result = select_tables("Gross sales by region", {"customers": SCHEMA["customers"]})
    assert result == ("customers",)


def test_repeatability():
    assert build_prompt("Gross sales by region", SCHEMA) == build_prompt("Gross sales by region", SCHEMA)
