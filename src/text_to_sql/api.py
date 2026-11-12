"""Local-only FastAPI adapter for the existing text-to-SQL pipeline.

Run via: uvicorn text_to_sql.api:app --host 127.0.0.1 --port 8000
Do not expose on 0.0.0.0 or the public internet: no authentication or
resource isolation has been implemented.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .pipeline import PipelineOutput, ask_database


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=500)


class ValidationCheck(BaseModel):
    name: str
    passed: bool | None
    description: str


class ValidationResponse(BaseModel):
    status: str
    score: int | None
    checks: list[ValidationCheck]
    warnings: list[str]


class ResultResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_ms: float


class QueryResponse(BaseModel):
    status: str
    message: str
    sql: str | None = None
    explanation: str | None = None
    referenced_tables: list[str] = Field(default_factory=list)
    options: list[str] = Field(default_factory=list)
    result: ResultResponse | None = None
    validation: ValidationResponse | None = None


def format_output(out: PipelineOutput) -> QueryResponse:
    """Serialize pipeline DTOs; model SQL is data, never an instruction."""
    validation = None
    if out.validation:
        validation = ValidationResponse(
            status=out.validation.status,
            score=out.validation.score,
            checks=[ValidationCheck(name=n, passed=ok, description=description)
                    for n, ok, description in out.validation.checks],
            warnings=list(out.validation.warnings),
        )
    result = None
    if out.result:
        result = ResultResponse(
            columns=out.result.columns,
            rows=out.result.rows,
            row_count=out.result.row_count,
            execution_ms=out.result.execution_ms,
        )
    return QueryResponse(
        status=out.status,
        message=out.message,
        sql=out.result.sql if out.result else (out.candidate.sql if out.candidate else None),
        explanation=out.candidate.explanation if out.candidate else None,
        referenced_tables=list(out.candidate.referenced_tables) if out.candidate else [],
        options=list(out.options),
        result=result,
        validation=validation,
    )


def create_app(
    *,
    database_path: str | Path | None = None,
    pipeline: Callable[[str, str | Path], PipelineOutput] = ask_database,
) -> FastAPI:
    """App factory allows the HTTP layer to be tested without Ollama."""
    path = Path(database_path or os.environ.get("TEXT_TO_SQL_DB", "data/sales.duckdb"))
    api = FastAPI(title="Text-to-SQL (Local Demo)", version="0.1.0")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}  # API process only; not model or DB readiness

    @api.post("/v1/query", response_model=QueryResponse)
    def query(request: QueryRequest) -> QueryResponse:
        if not path.is_file():
            raise HTTPException(status_code=503, detail="Demo database not found; run scripts/build_database.py")
        try:
            output = pipeline(request.question, path)
        except Exception:
            # No raw DB/model stack traces or SQL internals returned to clients.
            raise HTTPException(status_code=500, detail="Unexpected local pipeline error") from None
        return format_output(output)

    return api


app = create_app()
