"""Deterministic evaluator tests: no model download, no HTTP, no extra database."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from text_to_sql.evaluation import answers_match, load_cases, summarize, run_evaluation
from text_to_sql.sample_data import build_database


CASES = Path(__file__).resolve().parents[1] / "evaluation" / "cases.json"


def test_case_contract():
    cases = load_cases(CASES)
    assert len(cases) == 10
    assert sum(c.expected_status == "executed" for c in cases) == 8
    assert sum(c.expected_status == "clarification" for c in cases) == 2


def test_row_order_and_numeric_decimal_equivalence():
    assert answers_match([["West", "2.00"], ["East", 3]], [["East", "3.0"], ["West", 2]], 2, 2)


def test_rejects_missing_rows_and_extra_columns():
    assert not answers_match([["East", 3]], [["East", 3], ["West", 2]], 2, 2)
    assert not answers_match([["East", 3]], [["East", 3]], 2, 3)


def test_duplicate_rows_matter():
    assert not answers_match([["East", 3], ["East", 3]], [["East", 3], ["West", 3]], 2, 2)


def test_wrong_answer_not_counted_as_success():
    report = summarize([
        {"expected_status": "executed", "observed_status": "executed", "answer_correct": False, "validation_status": "pass", "latency_s": 1.0},
        {"expected_status": "executed", "observed_status": "executed", "answer_correct": True, "validation_status": "pass", "latency_s": 2.0},
        {"expected_status": "clarification", "observed_status": "clarification", "latency_s": 0.1},
    ])
    assert report["exact_answer_accuracy"] == 0.5
    assert report["wrong_answer_detection_rate"] == 0.0
    assert report["correct_clarifications"] == 1


def test_no_wrong_executed_answer_does_not_invent_detection_rate():
    report = summarize([{"expected_status": "executed", "observed_status": "blocked", "answer_correct": False, "validation_status": None, "latency_s": 0.1}])
    assert report["wrong_answer_detection_rate"] is None


def test_golden_queries_can_execute_safely(tmp_path):
    from text_to_sql.executor import execute_query
    from text_to_sql.guardrails import GuardrailPolicy
    from text_to_sql.schema import get_schema

    db = build_database(tmp_path / "sales.duckdb")
    policy = GuardrailPolicy(allowed_tables=frozenset(get_schema(db)))
    for case in load_cases(CASES):
        if case.reference_sql:
            got = execute_query(case.reference_sql, db, policy)
            assert got.row_count > 0, case.id


def test_benchmark_stub_demonstrates_failure_not_fake_success(tmp_path):
    db = build_database(tmp_path / "sales.duckdb")
    def stub(question, path):
        if "revenue by region" in question.lower() or "refund rate" in question.lower():
            return SimpleNamespace(status="clarification", result=None, candidate=None, validation=None)
        return SimpleNamespace(
            status="executed", candidate=None,
            result=SimpleNamespace(sql="SELECT 0", columns=["n"], rows=[[0]]),
            validation=SimpleNamespace(status="pass", score=100, warnings=()),
        )
    report = run_evaluation(db, CASES, ask=stub)
    assert report["metadata"]["mode"] == "injected-test-double"
    assert report["summary"]["exact_answer_matches"] == 0
    assert report["summary"]["correct_clarifications"] == 2
