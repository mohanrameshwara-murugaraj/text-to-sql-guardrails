import json
import pytest

from text_to_sql.llm import SQLCandidate, ModelResponseError, generate_candidate, parse_candidate
from text_to_sql.pipeline import ask_database
from text_to_sql.sample_data import build_database


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "sales.duckdb"
    build_database(path)
    return path


def test_parse_valid():
    c = parse_candidate('{"sql":"SELECT 1", "explanation":"ok", "referenced_tables":[]}')
    assert c.sql == "SELECT 1"


@pytest.mark.parametrize("payload", ["oops", "[]", '{"sql":3,"explanation":"x","referenced_tables":[]}',
                                      '{"sql":"SELECT 1","explanation":"x","referenced_tables":"customers"}'])
def test_parse_rejects_malformed(payload):
    with pytest.raises(ModelResponseError):
        parse_candidate(payload)


def test_adapter_with_fake_ollama_transport():
    def fake(req, timeout):
        body = json.loads(req.data)
        assert body["stream"] is False
        assert body["options"]["temperature"] == 0
        return json.dumps({"response": json.dumps({"sql": "SELECT 1", "explanation": "ok", "referenced_tables": []})}).encode()
    assert generate_candidate("hello", transport=fake).sql == "SELECT 1"


def test_adapter_blocks_non_local_endpoint():
    with pytest.raises(ValueError):
        generate_candidate("hello", endpoint="https://example.com/api/generate")


def test_ambiguous_question_does_not_call_model(db):
    def fail(_):
        raise AssertionError("model should not run")
    r = ask_database("Revenue by region", db, generator=fail)
    assert r.status == "clarification"
    assert len(r.options) == 2


def test_known_question_executes(db):
    def fake(_):
        return SQLCandidate("SELECT region, COUNT(*) AS customers FROM customers GROUP BY region ORDER BY region",
                            "Customer count per region", ("customers",))
    r = ask_database("How many customers by region?", db, generator=fake)
    assert r.status == "executed", r.message
    assert r.result is not None
    assert r.result.row_count == 4
    assert "LIMIT 1000" in r.result.sql


def test_dangerous_sql_is_blocked(db):
    r = ask_database("How many customers by region?", db,
                     generator=lambda _: SQLCandidate("DELETE FROM customers", "delete", ("customers",)))
    assert r.status == "blocked"


def test_out_of_scope_table_is_blocked(db):
    r = ask_database("How many customers by region?", db,
                     generator=lambda _: SQLCandidate("SELECT * FROM orders", "wrong table", ("orders",)))
    assert r.status == "blocked"


def test_llm_refusal_does_not_execute(db):
    r = ask_database("How many customers by region?", db,
                     generator=lambda _: SQLCandidate(None, "Cannot answer", ()))
    assert r.status == "refused"
