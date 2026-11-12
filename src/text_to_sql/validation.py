"""Deterministic semantic checks for a small synthetic business schema.

Not a general hallucination detector. Only supported question patterns receive
semantic assertions; unknown intents remain *unverified*. Scores are heuristic
signal summaries, not calibrated probabilities of correctness.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re

import sqlglot
from sqlglot import exp


@dataclass(frozen=True)
class ValidationReport:
    status: str  # pass | warning | unverified
    score: int | None  # heuristic score; not a probability
    checks: tuple[tuple[str, bool | None, str], ...]
    warnings: tuple[str, ...]


def _tokens(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def validate_answer(question: str, sql: str, columns: list[str], rows: list[list[Any]]) -> ValidationReport:
    """Flag provable mismatches for narrow question types; abstain otherwise.

    Called ONLY on SQL already approved and executed by the guardrail.
    Checks never grant permission to execute SQL.
    """
    checks: list[tuple[str, bool | None, str]] = []
    words = _tokens(question)
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
    except sqlglot.errors.ParseError:
        return ValidationReport("warning", 0, (("syntax", False, "Cannot parse executed SQL"),), ("SQL parse failed",))
    tables = {t.name.lower() for t in tree.find_all(exp.Table)}
    aggregates = list(tree.find_all(exp.Count, exp.Sum, exp.Avg))
    columns_used = [c.name.lower() for c in tree.find_all(exp.Column)]
    group = tree.args.get("group")
    group_cols = {c.name.lower() for c in group.find_all(exp.Column)} if group else set()
    sums = list(tree.find_all(exp.Sum))
    counts = list(tree.find_all(exp.Count))
    has_completed_filter = any(
        isinstance(n, exp.EQ)
        and ((isinstance(n.left, exp.Column) and n.left.name.lower() == "status" and isinstance(n.right, exp.Literal) and n.right.this.lower() == "completed")
             or (isinstance(n.right, exp.Column) and n.right.name.lower() == "status" and isinstance(n.left, exp.Literal) and n.left.this.lower() == "completed"))
        for n in tree.find_all(exp.EQ)
    )
    # A JOIN can multiply customer rows. COUNT(*) then counts joined rows,
    # not customers. Require an explicit distinct customer key when joined.
    joins = list(tree.find_all(exp.Join))
    customer_aliases = {
        (t.alias_or_name or t.name).lower()
        for t in tree.find_all(exp.Table)
        if t.name.lower() == "customers"
    }

    def counts_customer_entities(count: exp.Count) -> bool:
        arg = count.this
        if not joins and isinstance(arg, exp.Star):
            return True
        if isinstance(arg, exp.Distinct):
            expressions = arg.expressions
            if len(expressions) != 1 or not isinstance(expressions[0], exp.Column):
                return False
            col = expressions[0]
            return (col.name.lower() == "customer_id"
                    and (not joins or col.table.lower() in customer_aliases))
        return (not joins and isinstance(arg, exp.Column)
                and arg.name.lower() == "customer_id")

    # Specific supported intents only. All other questions abstain.
    customer_count = bool({"customer", "customers", "clients"} & words and {"how", "many"} <= words or "customers" in words and "count" in words)
    gross_sales = "gross" in words and ("sales" in words or "revenue" in words)
    by_region = "region" in words or "regions" in words
    if customer_count:
        checks.append(("customer_source", "customers" in tables, "Customer counts must read customers"))
        checks.append(("count_aggregate", bool(counts), "Customer counts require COUNT"))
        checks.append(("customer_count_semantics", any(counts_customer_entities(c) for c in counts), "Count customer entities; joined rows require COUNT(DISTINCT customers.customer_id)"))
        if by_region:
            checks.append(("region_group", "region" in group_cols, "Per-region counts require GROUP BY region"))
    elif gross_sales:
        checks.append(("sales_source", {"orders", "order_items"} <= tables, "Gross sales require orders and order_items"))
        checks.append(("sales_aggregate", bool(sums), "Gross sales require SUM"))
        checks.append(("sales_formula", any(
            {"quantity", "unit_price"} <= {c.name.lower() for c in s.find_all(exp.Column)}
            and s.find(exp.Mul) is not None for s in sums
        ), "Gross sales must aggregate quantity * unit_price"))
        checks.append(("completed_only", has_completed_filter, "Gross sales exclude non-completed orders"))
        if by_region:
            checks.append(("region_source", "customers" in tables, "Region requires customers"))
            checks.append(("region_group", "region" in group_cols, "Per-region sales require GROUP BY region"))
    else:
        checks.append(("semantic_alignment", None, "No deterministic verifier for this question type"))
    if not rows:
        checks.append(("nonempty_result", None, "Empty result; cannot establish whether expected"))
    if rows and any(len(row) != len(columns) for row in rows):
        checks.append(("result_shape", False, "Returned rows do not match column metadata"))
    else:
        checks.append(("result_shape", True, "Row width matches columns"))
    failed = [detail for _, ok, detail in checks if ok is False]
    unknown = any(ok is None for _, ok, _ in checks)
    decisive = [ok for _, ok, _ in checks if ok is not None]
    score = round(100 * sum(bool(ok) for ok in decisive) / len(decisive)) if decisive else None
    status = "warning" if failed else "unverified" if unknown else "pass"
    return ValidationReport(status, score, tuple(checks), tuple(failed + (["Some checks were inconclusive"] if unknown else [])))
