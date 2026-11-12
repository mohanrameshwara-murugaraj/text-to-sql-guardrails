"""Conservative SQL AST allowlist for read-only business analytics.

This is *not* the database security boundary. Also use database permissions,
read-only connections, execution timeouts, resource controls and audit logging.
"""
from dataclasses import dataclass

import sqlglot
from sqlglot import exp


class UnsafeQuery(ValueError):
    """SQL cannot be safely admitted by the current policy."""


@dataclass(frozen=True)
class GuardrailPolicy:
    allowed_tables: frozenset[str]
    max_rows: int = 1000

    def __post_init__(self) -> None:
        if self.max_rows < 1:
            raise ValueError("max_rows must be positive")
        if not self.allowed_tables:
            raise ValueError("allowed_tables must not be empty")


ALLOWED_NODES = (
    exp.Select, exp.From, exp.Table, exp.Column, exp.Identifier,
    exp.Star, exp.Where, exp.And, exp.Or, exp.Not, exp.EQ, exp.NEQ,
    exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Paren, exp.Literal,
    exp.Order, exp.Ordered, exp.Limit, exp.Is, exp.Null, exp.Between,
    exp.In, exp.Neg, exp.Join, exp.Alias, exp.TableAlias, exp.Group,
    exp.Having, exp.Count, exp.Sum, exp.Avg, exp.Round, exp.Distinct,
    exp.Add, exp.Sub, exp.Mul, exp.Div,
)


def validate_sql(sql: str, policy: GuardrailPolicy) -> str:
    """Validate a narrow single-SELECT subset; return SQL capped by LIMIT.

    JOINs must be explicit INNER or LEFT equijoins between qualified columns.
    Unknown AST constructs fail closed. Column existence and relationships
    are not checked yet and will require schema-aware validation.
    """
    if not sql or not sql.strip():
        raise UnsafeQuery("Empty SQL")
    try:
        statements = sqlglot.parse(sql, read="duckdb", error_level="RAISE")
    except sqlglot.errors.ParseError as exc:
        raise UnsafeQuery("Invalid SQL syntax") from exc
    if len(statements) != 1 or not isinstance(statements[0], exp.Select):
        raise UnsafeQuery("Exactly one SELECT statement is allowed")
    tree = statements[0]

    for node in tree.walk():
        if not isinstance(node, ALLOWED_NODES):
            raise UnsafeQuery(f"Unsupported or unsafe SQL construct: {node.key}")

    from_node = tree.args.get("from_")
    if from_node is None or not isinstance(from_node.this, exp.Table):
        raise UnsafeQuery("Query must start from an allowed physical table")

    tables = list(tree.find_all(exp.Table))
    allowed = {t.lower() for t in policy.allowed_tables}
    names = {}
    for table in tables:
        if table.name.lower() not in allowed or table.db or table.catalog:
            raise UnsafeQuery("Only unqualified allowlisted tables are permitted")
        alias = table.alias_or_name.lower()
        if alias in names:
            raise UnsafeQuery("Duplicate table alias")
        names[alias] = table.name.lower()
    joins = tree.args.get("joins") or []
    if len(tables) != len(joins) + 1:
        raise UnsafeQuery("Unexpected table reference")

    for join in joins:
        if not isinstance(join.this, exp.Table):
            raise UnsafeQuery("Only physical tables may be joined")
        if join.args.get("using") is not None:
            raise UnsafeQuery("USING joins are not supported; use explicit ON")
        method = (join.args.get("method") or "").upper()
        side = (join.args.get("side") or "").upper()
        kind = (join.args.get("kind") or "").upper()
        if method or side not in ("", "LEFT") or kind not in ("", "INNER", "OUTER"):
            raise UnsafeQuery("Only INNER and LEFT joins are permitted")
        if side == "LEFT" and kind not in ("", "OUTER"):
            raise UnsafeQuery("Unsupported join type")
        on = join.args.get("on")
        if not isinstance(on, exp.EQ) or not all(isinstance(v, exp.Column) for v in (on.left, on.right)):
            raise UnsafeQuery("JOIN requires ON alias.column = alias.column")
        a, b = on.left, on.right
        if not a.table or not b.table or a.table.lower() == b.table.lower():
            raise UnsafeQuery("JOIN columns must reference distinct table aliases")

    # Only declared aliases may be referenced. Multiple tables require
    # explicit qualification to prevent ambiguous columns.
    output_aliases = {item.alias.lower() for item in tree.expressions if isinstance(item, exp.Alias)}
    for column in tree.find_all(exp.Column):
        if column.is_star:
            raise UnsafeQuery("SELECT alias.* is not supported")
        is_order_alias = (
            not column.table
            and column.name.lower() in output_aliases
            and isinstance(column.parent, exp.Ordered)
        )
        if (len(tables) > 1 and not column.table and not is_order_alias) or (column.table and column.table.lower() not in names):
            raise UnsafeQuery("Unknown or missing table alias")
        if column.db or column.catalog:
            raise UnsafeQuery("Qualified database or catalog names are not allowed")

    limit = tree.args.get("limit")
    if limit is not None:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int:
            raise UnsafeQuery("LIMIT must be an integer literal")
        requested = int(value.this)
        if requested < 1:
            raise UnsafeQuery("LIMIT must be positive")
    else:
        requested = policy.max_rows
    return tree.copy().limit(min(requested, policy.max_rows)).sql(dialect="duckdb")
