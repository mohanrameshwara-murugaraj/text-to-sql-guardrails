"""Local NL-to-SQL pipeline with deterministic safety gate.

This pipeline does NOT verify that SQL answers the question. That is the
next evaluation milestone; never present its result as factually verified.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .executor import QueryResult, execute_query
from .guardrails import GuardrailPolicy, UnsafeQuery
from .llm import SQLCandidate, ModelResponseError, generate_candidate
from .prompt_engine import build_prompt
from .schema import get_schema
from .validation import ValidationReport, validate_answer


@dataclass(frozen=True)
class PipelineOutput:
    status: str  # clarification | refused | blocked | executed | error
    message: str
    candidate: SQLCandidate | None = None
    result: QueryResult | None = None
    options: tuple[str, ...] = ()
    validation: ValidationReport | None = None


def ask_database(
    question: str,
    database_path: str | Path,
    *,
    generator: Callable[[str], SQLCandidate] = generate_candidate,
    executor: Callable[[str, str | Path, GuardrailPolicy], QueryResult] = execute_query,
) -> PipelineOutput:
    """Prepare prompt, generate candidate, validate then execute read-only.

    The LLM's referenced_tables are claims only; the *actual* allowed table
    set is derived from schema selection, and SQL AST validation controls it.
    """
    schema = get_schema(database_path)
    prepared = build_prompt(question, schema)
    if prepared.clarification is not None:
        return PipelineOutput("clarification", prepared.clarification.reason,
                              options=prepared.clarification.options)
    assert prepared.prompt is not None
    try:
        candidate = generator(prepared.prompt)
    except ModelResponseError as exc:
        return PipelineOutput("error", str(exc))
    if candidate.sql is None:
        return PipelineOutput("refused", candidate.explanation, candidate=candidate)
    if not set(candidate.referenced_tables) <= set(prepared.selected_tables):
        return PipelineOutput("blocked", "Model claimed tables outside the selected schema", candidate=candidate)
    policy = GuardrailPolicy(allowed_tables=frozenset(prepared.selected_tables), max_rows=1000)
    try:
        result = executor(candidate.sql, database_path, policy)
    except UnsafeQuery as exc:
        return PipelineOutput("blocked", f"SQL safety policy rejected the candidate: {exc}", candidate=candidate)
    except Exception as exc:
        # Local development only: do not echo raw DB errors to public clients.
        return PipelineOutput("error", f"Database execution failed ({type(exc).__name__})", candidate=candidate)
    report = validate_answer(question, result.sql, result.columns, result.rows)
    return PipelineOutput("executed",
                          f"Executed safely; semantic checks: {report.status}. Not independently proven correct.",
                          candidate=candidate, result=result, validation=report)
