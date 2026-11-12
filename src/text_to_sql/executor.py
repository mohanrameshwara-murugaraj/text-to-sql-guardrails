"""Read-only execution boundary for already allowlisted analytic SELECT queries.

This is an educational, local-only sandbox, not a hostile-code isolation system.
Do not expose it to untrusted network clients without process-level isolation,
authorization, resource/time controls and an independently reviewed policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

import duckdb

from .guardrails import GuardrailPolicy, validate_sql


@dataclass(frozen=True)
class QueryResult:
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    execution_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "execution_ms": self.execution_ms,
        }


def _json_safe(value: Any) -> Any:
    """Convert DuckDB scalar values into JSON-compatible values.

    Decimal is serialized as string to avoid silently losing monetary precision.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    return value


def execute_query(sql: str, database_path: str | Path, policy: GuardrailPolicy) -> QueryResult:
    """Validate and execute one permitted SELECT in a fresh read-only connection.

    Raises UnsafeQuery for policy violations; DuckDB errors propagate for invalid
    table columns/SQL. Output limits protect response size, *not* query scan cost.
    """
    # Validate before even opening the database.
    safe_sql = validate_sql(sql, policy)
    db = Path(database_path).expanduser().resolve(strict=True)
    if not db.is_file():
        raise ValueError("Database path must be an existing file")

    start = perf_counter()
    with duckdb.connect(str(db), read_only=True) as connection:
        # Fail closed if external-access restrictions cannot be enabled.
        # This is defense in depth: the SQL AST policy is the first line.
        connection.execute("SET enable_external_access = false")
        connection.execute("SET threads = 1")
        connection.execute("SET memory_limit = '256MB'")
        cursor = connection.execute(safe_sql)
        columns = [item[0] for item in cursor.description]
        raw_rows = cursor.fetchmany(policy.max_rows)

    elapsed = round((perf_counter() - start) * 1000, 3)
    rows = [[_json_safe(value) for value in record] for record in raw_rows]
    return QueryResult(
        sql=safe_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        execution_ms=elapsed,
    )
