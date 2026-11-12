# Milestone 2: Deterministic analytics data

This overlay adds files to the existing starter repository; it does not replace the guardrails module or its tests.

From the existing repository root (with `.venv` activated):

```bash
python scripts/build_database.py
pytest -q
```

You should see five table names printed and all 20 tests passing (17 existing + 3 new). The database is generated at `data/sales.duckdb`.

**Important:** Running `python scripts/build_database.py` replaces `data/sales.duckdb` with fresh synthetic data. Do not run it against any database containing work you need to preserve.

This phase does **not** execute user-generated SQL or establish real runtime security. SQLAlchemy-based schema extraction, safe SQL execution, joins and aggregation support are planned for subsequent phases; the present read-only metadata query uses DuckDB's `information_schema` directly.
