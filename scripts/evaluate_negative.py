"""Deterministic pattern-level semantic regression report; not a live LLM benchmark.

Run from the project root: python scripts/evaluate_negative.py
Writes results/negative_cases_latest.json. No Ollama needed.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from text_to_sql.validation import validate_answer

QUESTION = "How many customers are in each region?"
COLUMNS = ["region", "customer_count"]
# Dummy shape-only result to exercise semantic rule detection, not computed DB output.
ROWS = [["East", 10]]

CASES = [
    ("customer_count_plain", "SELECT region, COUNT(*) FROM customers GROUP BY region", "pass"),
    ("joined_rows_wrong", "SELECT c.region, COUNT(*) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.region", "warning"),
    ("joined_orders_wrong", "SELECT c.region, COUNT(o.order_id) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.region", "warning"),
    ("joined_distinct_customer", "SELECT c.region, COUNT(DISTINCT c.customer_id) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.region", "pass"),
    ("joined_distinct_order_wrong", "SELECT c.region, COUNT(DISTINCT o.order_id) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.region", "warning"),
]


def main() -> None:
    outcomes = []
    for case_id, sql, expected in CASES:
        report = validate_answer(QUESTION, sql, COLUMNS, ROWS)
        outcomes.append({
            "id": case_id,
            "expected_status": expected,
            "observed_status": report.status,
            "as_expected": report.status == expected,
            "failed_checks": [n for n, passed, _ in report.checks if passed is False],
        })
    total = len(outcomes)
    matched = sum(x["as_expected"] for x in outcomes)
    output = {
        "metadata": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "mode": "fixed-sql-pattern-regression",
            "notes": "Uses a fixed, synthetic result shape to test SQL semantic rules. "
                     "No LLM, query execution, or measured generalized detection recall.",
        },
        "summary": {"cases": total, "expected_outcomes_matched": matched},
        "cases": outcomes,
    }
    path = Path("results/negative_cases_latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output["summary"], indent=2))
    print(f"Saved to: {path}")
    if matched != total:
        raise SystemExit("Unexpected semantic regression outcomes")


if __name__ == "__main__":
    main()
