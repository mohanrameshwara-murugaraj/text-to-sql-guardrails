"""Reproducible, small local benchmark. Reports observations, not certification.

Gold answers are independently computed from hand-written reference SQL.
Live calls use the real local model unless a test explicitly injects a stub.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
import json


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    expected_status: str
    reference_sql: str | None = None


def load_cases(path: str | Path) -> list[EvalCase]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Expected a nonempty JSON array of evaluation cases")
    cases = []
    ids = set()
    for item in raw:
        case = EvalCase(**item)
        if not case.id or case.id in ids or not case.question.strip():
            raise ValueError("Duplicate ID, missing ID, or empty question")
        if case.expected_status not in {"executed", "clarification"}:
            raise ValueError("Unsupported expected_status")
        if (case.expected_status == "executed") != bool(case.reference_sql):
            raise ValueError("Only executed cases require reference_sql")
        ids.add(case.id)
        cases.append(case)
    return cases


def _cell(value: Any) -> tuple[str, str]:
    """Canonicalize scalar values, preserving numeric meaning and NULLs.

    This benchmark intentionally treats column aliases and output row order
    as irrelevant. It does NOT forgive extra/missing columns or rows.
    """
    if value is None:
        return ("null", "")
    if isinstance(value, bool):
        return ("bool", str(value))
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            num = Decimal(str(value))
            if not num.is_finite():
                return ("nonfinite", str(value))
            return ("number", str(num.normalize()))
        except InvalidOperation:
            return ("other", str(value))
    # String output can represent a decimal because QueryResult JSON-serializes
    # DECIMAL as a string. Only parse it when both values are numeric-like.
    if isinstance(value, str):
        return ("string", value)
    return ("other", str(value))


def _cell_equal(left: Any, right: Any) -> bool:
    a, b = _cell(left), _cell(right)
    if a == b:
        return True
    if a[0] in {"number", "string"} and b[0] in {"number", "string"}:
        try:
            return Decimal(a[1]) == Decimal(b[1])
        except InvalidOperation:
            return False
    return False


def answers_match(actual: list[list[Any]], gold: list[list[Any]], actual_columns: int, gold_columns: int) -> bool:
    """Exact multiset-of-rows match, ignoring order and column names.

    A small benchmark deliberately uses only exact arithmetic for gold SQL.
    The implementation is quadratic in row count (fine for <=1000 rows).
    """
    if actual_columns != gold_columns or len(actual) != len(gold):
        return False
    if any(len(r) != actual_columns for r in actual) or any(len(r) != gold_columns for r in gold):
        return False
    remaining = list(gold)
    for row in actual:
        match = next((i for i, expected in enumerate(remaining)
                      if all(_cell_equal(x, y) for x, y in zip(row, expected))), None)
        if match is None:
            return False
        remaining.pop(match)
    return not remaining


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [x for x in cases if x["expected_status"] == "executed"]
    ambiguous = [x for x in cases if x["expected_status"] == "clarification"]
    n_ok = sum(x.get("answer_correct") is True for x in answerable)
    n_executed = sum(x.get("observed_status") == "executed" for x in answerable)
    n_clarified = sum(x.get("observed_status") == "clarification" for x in ambiguous)
    flagged_wrong = [x for x in answerable
                     if x.get("observed_status") == "executed" and x.get("answer_correct") is False]
    validators_flagged = sum(x.get("validation_status") == "warning" for x in flagged_wrong)
    timings = [x["latency_s"] for x in cases if x.get("latency_s") is not None]
    return {
        "answerable_cases": len(answerable),
        "exact_answer_matches": n_ok,
        "exact_answer_accuracy": round(n_ok / len(answerable), 4) if answerable else None,
        "executed_answerable_cases": n_executed,
        "execution_rate": round(n_executed / len(answerable), 4) if answerable else None,
        "ambiguous_cases": len(ambiguous),
        "correct_clarifications": n_clarified,
        "clarification_rate": round(n_clarified / len(ambiguous), 4) if ambiguous else None,
        "wrong_executed_answers": len(flagged_wrong),
        "wrong_answers_flagged_by_validator": validators_flagged,
        "wrong_answer_detection_rate": (round(validators_flagged / len(flagged_wrong), 4)
                                        if flagged_wrong else None),
        "mean_latency_s": round(sum(timings) / len(timings), 3) if timings else None,
        "statuses": dict(Counter(x.get("observed_status", "unknown") for x in cases)),
    }


def run_evaluation(
    database_path: str | Path,
    case_path: str | Path,
    *,
    ask: Callable[[str, str | Path], Any] | None = None,
    reference_execute: Callable[[str, str | Path], tuple[list[str], list[list[Any]]]] | None = None,
) -> dict[str, Any]:
    from .pipeline import ask_database
    from .guardrails import GuardrailPolicy
    from .executor import execute_query
    from .schema import get_schema

    cases = load_cases(case_path)
    ask = ask or ask_database
    if reference_execute is None:
        allowed = frozenset(get_schema(database_path))
        policy = GuardrailPolicy(allowed_tables=allowed)
        def reference_execute(sql: str, db: str | Path) -> tuple[list[str], list[list[Any]]]:
            result = execute_query(sql, db, policy)
            return result.columns, result.rows
    outcomes: list[dict[str, Any]] = []
    for case in cases:
        start = perf_counter()
        item: dict[str, Any] = {
            "id": case.id, "question": case.question, "expected_status": case.expected_status,
        }
        try:
            # Gold calculation does NOT use the LLM's generated SQL.
            if case.reference_sql is not None:
                gold_columns, gold_rows = reference_execute(case.reference_sql, database_path)
            else:
                gold_columns, gold_rows = [], []
            output = ask(case.question, database_path)
            item["observed_status"] = output.status
            item["sql"] = output.result.sql if output.result else (output.candidate.sql if output.candidate else None)
            item["validation_status"] = output.validation.status if output.validation else None
            item["validation_score"] = output.validation.score if output.validation else None
            item["warnings"] = list(output.validation.warnings) if output.validation else []
            if case.expected_status == "executed":
                item["answer_correct"] = bool(
                    output.status == "executed" and output.result is not None and
                    answers_match(output.result.rows, gold_rows, len(output.result.columns), len(gold_columns))
                )
            else:
                item["clarification_correct"] = output.status == "clarification"
        except Exception as exc:
            item["observed_status"] = "exception"
            item["error_type"] = type(exc).__name__
            if case.expected_status == "executed":
                item["answer_correct"] = False
            else:
                item["clarification_correct"] = False
        item["latency_s"] = round(perf_counter() - start, 3)
        outcomes.append(item)
    return {
        "metadata": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "database": str(database_path),
            "cases_path": str(case_path),
            "case_count": len(cases),
            "mode": "live" if ask is ask_database else "injected-test-double",
            "notes": "One run per question. Scores are not calibrated correctness probabilities. "
                     "This is a small schema-specific benchmark, not production certification.",
        },
        "summary": summarize(outcomes),
        "cases": outcomes,
    }
