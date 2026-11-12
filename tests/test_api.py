"""HTTP adapter tests; no live Ollama connection required."""
from pathlib import Path

from fastapi.testclient import TestClient

from text_to_sql.api import create_app, format_output
from text_to_sql.executor import QueryResult
from text_to_sql.llm import SQLCandidate
from text_to_sql.pipeline import PipelineOutput
from text_to_sql.validation import ValidationReport


def _client(tmp_path: Path, output: PipelineOutput) -> TestClient:
    db = tmp_path / "sales.duckdb"
    db.write_bytes(b"fixture: fake pipeline never opens this file")
    return TestClient(create_app(database_path=db, pipeline=lambda question, path: output))


def test_executed_response_contains_results_and_validation(tmp_path):
    out = PipelineOutput(
        "executed", "Executed safely", candidate=SQLCandidate("SELECT 1", "example", ("customers",)),
        result=QueryResult("SELECT 1 LIMIT 1000", ["n"], [[1]], 1, 3.4),
        validation=ValidationReport("pass", 100, (("result_shape", True, "shape ok"),), ()),
    )
    with _client(tmp_path, out) as client:
        response = client.post("/v1/query", json={"question": "Count customers"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "executed"
    assert body["sql"] == "SELECT 1 LIMIT 1000"
    assert body["result"]["rows"] == [[1]]
    assert body["validation"]["checks"][0]["passed"] is True


def test_clarification_returns_options(tmp_path):
    with _client(tmp_path, PipelineOutput("clarification", "Which revenue?", options=("gross", "net"))) as client:
        response = client.post("/v1/query", json={"question": "Revenue by region"})
    assert response.status_code == 200
    assert response.json()["options"] == ["gross", "net"]
    assert response.json()["result"] is None


def test_blocked_sql_does_not_return_results(tmp_path):
    out = PipelineOutput("blocked", "SQL safety policy rejected the candidate", candidate=SQLCandidate("DELETE FROM customers", "bad", ("customers",)))
    with _client(tmp_path, out) as client:
        response = client.post("/v1/query", json={"question": "Delete all customers"})
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["result"] is None


def test_invalid_requests_rejected(tmp_path):
    with _client(tmp_path, PipelineOutput("refused", "no")) as client:
        assert client.post("/v1/query", json={"question": " "}).status_code == 422
        assert client.post("/v1/query", json={"question": "abc", "sql": "DROP TABLE x"}).status_code == 422
        assert client.post("/v1/query", json={"question": "x" * 501}).status_code == 422


def test_missing_database_returns_503(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "missing.duckdb")) as client:
        response = client.post("/v1/query", json={"question": "Count customers"})
    assert response.status_code == 503


def test_unexpected_errors_are_not_exposed(tmp_path):
    db = tmp_path / "sales.duckdb"
    db.write_bytes(b"fake")
    def fail(question, path):
        raise RuntimeError("private stack trace / secret")
    with TestClient(create_app(database_path=db, pipeline=fail)) as client:
        response = client.post("/v1/query", json={"question": "Count customers"})
    assert response.status_code == 500
    assert "secret" not in response.text


def test_health_is_process_only(tmp_path):
    with TestClient(create_app(database_path=tmp_path / "missing.duckdb")) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_unverified_validation_serializes_unknown_check():
    out = PipelineOutput("executed", "ok", validation=ValidationReport("unverified", None, (("alignment", None, "No verifier"),), ("Unknown",)))
    data = format_output(out).model_dump()
    assert data["validation"]["checks"][0]["passed"] is None
    assert data["validation"]["score"] is None
