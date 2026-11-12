"""Deterministic schema selection and LLM prompt construction.

No LLM call happens here. SQL from any model must still pass the validator
and read-only executor. The synthetic business glossary is the source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence
import re

Schema = Mapping[str, Sequence[Mapping[str, object]]]

RELATIONSHIPS = (
    ("orders", "customer_id", "customers", "customer_id"),
    ("order_items", "order_id", "orders", "order_id"),
    ("order_items", "product_id", "products", "product_id"),
    ("refunds", "order_id", "orders", "order_id"),
)

# Handwritten, schema-specific terms. No embeddings or network dependencies.
TABLE_TERMS: dict[str, tuple[str, ...]] = {
    "customers": ("customer", "customers", "client", "clients", "region", "segment"),
    "orders": ("order", "orders", "purchase", "purchases", "date", "month", "year", "status"),
    "order_items": ("sales", "gross", "gmv", "revenue", "quantity", "units", "items", "amount"),
    "products": ("product", "products", "category", "categories"),
    "refunds": ("refund", "refunds", "refunded"),
}

FEW_SHOTS = (
    (
        "How many customers are in each region?",
        "SELECT region, COUNT(*) AS customer_count FROM customers GROUP BY region ORDER BY region LIMIT 1000",
    ),
    (
        "What are completed order counts by region?",
        "SELECT c.region, COUNT(*) AS completed_orders FROM customers c "
        "JOIN orders o ON c.customer_id = o.customer_id "
        "WHERE o.status = 'completed' GROUP BY c.region ORDER BY c.region LIMIT 1000",
    ),
    (
        "What are gross sales by region for completed orders?",
        "SELECT c.region, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS gross_sales "
        "FROM customers c JOIN orders o ON c.customer_id = o.customer_id "
        "JOIN order_items oi ON o.order_id = oi.order_id "
        "WHERE o.status = 'completed' GROUP BY c.region ORDER BY gross_sales DESC LIMIT 1000",
    ),
)


@dataclass(frozen=True)
class Clarification:
    question: str
    reason: str
    options: tuple[str, ...]


@dataclass(frozen=True)
class PromptResult:
    question: str
    selected_tables: tuple[str, ...]
    prompt: str | None
    clarification: Clarification | None


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def detect_ambiguity(question: str) -> Clarification | None:
    """Fail closed for two known business-definition ambiguities."""
    words = _terms(question)
    if {"refund", "rate"} <= words or {"refunds", "rate"} <= words:
        return Clarification(question, "Refund rate has multiple valid denominators.", (
            "Percentage of completed orders with at least one refund",
            "Refund amount divided by gross merchandise value",
        ))
    # 'revenue' is intentionally not assumed to mean gross or net.
    if "revenue" in words and not ({"gross", "net"} & words):
        return Clarification(question, "Revenue is ambiguous in this synthetic dataset.", (
            "Gross sales (completed-order GMV before refunds)",
            "Net revenue (completed-order GMV minus recorded refunds)",
        ))
    return None


def select_tables(question: str, schema: Schema) -> tuple[str, ...]:
    """Keyword shortlist plus required FK bridge tables.

    This is a transparent baseline, not semantic retrieval. Keep all selected
    names allowlisted by the supplied schema.
    """
    words = _terms(question)
    available = set(schema)
    requested = {
        table for table, terms in TABLE_TERMS.items()
        if table in available and (set(terms) & words)
    }
    if not requested:
        return ()
    # Sales measures require completed orders, and refunds need order context.
    if "order_items" in requested or "refunds" in requested:
        requested.add("orders")
    # Products and customers often require an order bridge when used together.
    if "products" in requested and "customers" in requested:
        requested.update(("orders", "order_items"))
    if "products" in requested and "orders" in requested:
        requested.add("order_items")
    if "refunds" in requested and "customers" in requested:
        requested.add("orders")
    return tuple(sorted(requested & available))


def build_prompt(question: str, schema: Schema) -> PromptResult:
    """Construct a prompt or a clarification; never guesses unknown schema."""
    if not question or not question.strip():
        raise ValueError("Question must not be empty")
    clarification = detect_ambiguity(question)
    if clarification:
        return PromptResult(question, (), None, clarification)
    chosen = select_tables(question, schema)
    if not chosen:
        return PromptResult(question, (), None, Clarification(
            question,
            "No relevant tables could be identified from the supported schema.",
            ("Rephrase using customers, orders, products, sales, or refunds",),
        ))
    schema_lines: list[str] = []
    for table in chosen:
        columns = schema[table]
        if not columns:
            raise ValueError(f"Schema has no columns for table {table}")
        formatted = ", ".join(f"{c['name']} ({c['type']})" for c in columns)
        schema_lines.append(f"- {table}: {formatted}")
    relationships = [
        f"- {a}.{ac} = {b}.{bc}"
        for a, ac, b, bc in RELATIONSHIPS if a in chosen and b in chosen
    ]
    # Few-shots use other allowlisted tables when necessary; instructions clearly
    # restrict generated SQL to selected tables only.
    examples = [
        (q, sql) for q, sql in FEW_SHOTS
        if ({name for name in TABLE_TERMS if re.search(r"\b" + name + r"\b", sql)} <= set(chosen))
    ]
    prompt = "\n".join([
        "You generate candidate DuckDB SELECT statements for a synthetic sales database.",
        "Return ONLY a JSON object with keys: sql, explanation, referenced_tables.",
        "Never invent columns, tables, joins, values, or business definitions.",
        "Use only the tables listed below. Only INNER/LEFT equijoins; no subqueries or CTEs.",
        "Allowed aggregates: COUNT, SUM, AVG, ROUND. Always use LIMIT <= 1000.",
        "Never emit DDL, DML, file access, external functions, or multiple statements.",
        "If the question cannot be answered with these tables, return sql as null and explain why.",
        "Gross sales = SUM(quantity * unit_price) on completed orders before refunds.",
        "Net revenue = gross sales minus recorded refunds, with per-order refund aggregation to avoid fanout.",
        "Do not attempt unsupported net-revenue SQL if subqueries would be required.",
        "Available schema:", *schema_lines,
        "Relationships:", *(relationships or ["- None selected"]),
        "Examples:", *[f"Q: {q}\nSQL: {sql}" for q, sql in examples],
        f"User question: {question}",
    ])
    return PromptResult(question, chosen, prompt, None)
