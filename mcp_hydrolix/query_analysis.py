"""Static analysis of Hydrolix SELECT queries to surface common foot-guns.

Advisory only — `analyze_sql` returns findings; it never raises on
user-content issues. The intended consumers are MCP tools (`analyze_query`,
`find_bad_queries`) and any future linter/CI integration.

DESIGN NOTE — why we never recommend LIMIT:

In Hydrolix, LIMIT does not reduce cluster load. The query head and peers
still scan every matching partition from S3, hit the catalog, fan out across
peers, and materialize all matching rows; LIMIT is applied only at the very
end before returning to the client. The expensive work is already done by
then. So `SELECT * FROM logs LIMIT 10` against an unbounded time range is just
as damaging as the same query without LIMIT.

The analyzer therefore steers callers toward predicates that actually drive
partition pruning: a bounded time-range predicate on the primary-key timestamp
column, with the column unwrapped (no `toDate(...)`/`toStartOfHour(...)`
around it inside the predicate).
"""

import logging
from typing import Iterable, List, Optional

import sqlglot
import sqlglot.errors as sqlglot_errors
import sqlglot.expressions as exp

from mcp_hydrolix.models import Finding, QueryAnalysis

logger = logging.getLogger("mcp-hydrolix")


def analyze_sql(sql: str, timestamp_column: str = "timestamp") -> QueryAnalysis:
    """Run static checks on a Hydrolix SELECT query.

    `timestamp_column` defaults to "timestamp" — the most common PK name. Pass
    the table's actual PK name (from get_table_info) when known; tables whose
    PK is named differently (e.g. `day_ts`, `dt`) will otherwise be flagged
    with NO_TIME_RANGE even when they have a perfectly bounded predicate.
    """
    findings: List[Finding] = []
    try:
        parsed = sqlglot.parse_one(sql, dialect="clickhouse")
    except sqlglot_errors.SqlglotError as e:
        findings.append(
            Finding(
                code="PARSE_ERROR",
                severity="warn",
                message=f"Could not parse the query as ClickHouse SQL: {e}. Static checks were skipped.",
            )
        )
        return QueryAnalysis(ok=False, findings=findings, parsed_tables=[])

    findings.extend(_check_time_range(parsed, timestamp_column))
    findings.extend(_check_select_star(parsed))
    findings.extend(_check_broad_like(parsed))

    tables = sorted(
        {f"{t.db}.{t.name}" if t.db else t.name for t in parsed.find_all(exp.Table) if t.name}
    )
    ok = not any(f.severity == "high" for f in findings)
    return QueryAnalysis(ok=ok, findings=findings, parsed_tables=tables)


# ---- Time-range checks --------------------------------------------------------


def _check_time_range(parsed: exp.Expression, ts_col: str) -> List[Finding]:
    where = parsed.find(exp.Where)
    if where is None:
        return [_no_time_range_finding(ts_col, reason="query has no WHERE clause")]

    ts_predicates = list(_iter_ts_predicates(where, ts_col))
    if not ts_predicates:
        return [_no_time_range_finding(ts_col, reason="WHERE has no predicate on the timestamp PK")]

    findings: List[Finding] = []

    if any(_ts_side_is_wrapped(p, ts_col) for p in ts_predicates):
        findings.append(
            Finding(
                code="FN_ON_TS_PK",
                severity="high",
                message=(
                    f"At least one predicate wraps `{ts_col}` in a function or cast "
                    f"(e.g. `toDate({ts_col})`). This defeats partition pruning — "
                    f"the query head cannot use the timestamp index and will read every partition."
                ),
                suggested_rewrite=(
                    f"Compare the raw timestamp column to a value: "
                    f"`{ts_col} >= '...' AND {ts_col} < '...'`."
                ),
            )
        )

    has_lower = any(_is_lower_bound(p, ts_col) for p in ts_predicates)
    has_upper = any(_is_upper_bound(p, ts_col) for p in ts_predicates)
    has_eq_or_set = any(_is_equality_or_set(p, ts_col) for p in ts_predicates)
    if not has_eq_or_set and not (has_lower and has_upper):
        missing = "upper" if has_lower else "lower"
        findings.append(
            Finding(
                code="UNBOUNDED_TIME_RANGE",
                severity="warn",
                message=(
                    f"Predicate on `{ts_col}` is open-ended (missing {missing} bound). "
                    f"The query may scan more partitions than intended."
                ),
                suggested_rewrite=(f"Add the missing bound: `{ts_col} >= ... AND {ts_col} < ...`."),
            )
        )

    return findings


def _no_time_range_finding(ts_col: str, *, reason: str) -> Finding:
    return Finding(
        code="NO_TIME_RANGE",
        severity="high",
        message=(
            f"{reason}. Without a time-range filter on `{ts_col}`, the query reads every "
            f"partition for the referenced tables — a common cause of query-head OOM and "
            f"catalog overload. (Note: if this table's primary-key timestamp is not named "
            f"`{ts_col}`, pass the correct name as `timestamp_column`.)"
        ),
        suggested_rewrite=(
            f"Add a bounded predicate on the timestamp PK, e.g. "
            f"`WHERE {ts_col} >= now() - INTERVAL 1 HOUR AND {ts_col} < now()`."
        ),
    )


def _iter_ts_predicates(where: exp.Where, ts_col: str) -> Iterable[exp.Expression]:
    """Yield comparison/membership nodes that reference the timestamp column."""
    comparison_types = (
        exp.GT,
        exp.GTE,
        exp.LT,
        exp.LTE,
        exp.EQ,
        exp.NEQ,
        exp.In,
        exp.Between,
    )
    for node in where.walk():
        if isinstance(node, comparison_types) and _references_column(node, ts_col):
            yield node


def _references_column(node: exp.Expression, name: str) -> bool:
    name_l = name.lower()
    return any(isinstance(c, exp.Column) and c.name.lower() == name_l for c in node.walk())


def _ts_side(node: exp.Expression, ts_col: str) -> Optional[exp.Expression]:
    """Return the operand of a comparison that contains `ts_col`, else None."""
    lhs = getattr(node, "this", None)
    rhs = getattr(node, "expression", None)
    if lhs is not None and _references_column(lhs, ts_col):
        return lhs
    if rhs is not None and _references_column(rhs, ts_col):
        return rhs
    return None


def _ts_side_is_wrapped(node: exp.Expression, ts_col: str) -> bool:
    """True iff `ts_col` is inside a function/cast on this side of the comparison."""
    side = _ts_side(node, ts_col)
    if side is None:
        return False
    # Bare column reference — no wrapping.
    if isinstance(side, exp.Column) and side.name.lower() == ts_col.lower():
        return False
    return True


def _is_lower_bound(node: exp.Expression, ts_col: str) -> bool:
    """True iff this predicate establishes a lower bound on ts_col."""
    if isinstance(node, exp.Between):
        return _references_column(node.this, ts_col)
    ts_l = ts_col.lower()
    if isinstance(node, (exp.GT, exp.GTE)):
        # ts > value
        return isinstance(node.this, exp.Column) and node.this.name.lower() == ts_l
    if isinstance(node, (exp.LT, exp.LTE)):
        # value < ts → lower bound on ts
        return isinstance(node.expression, exp.Column) and node.expression.name.lower() == ts_l
    return False


def _is_upper_bound(node: exp.Expression, ts_col: str) -> bool:
    """True iff this predicate establishes an upper bound on ts_col."""
    if isinstance(node, exp.Between):
        return _references_column(node.this, ts_col)
    ts_l = ts_col.lower()
    if isinstance(node, (exp.LT, exp.LTE)):
        # ts < value
        return isinstance(node.this, exp.Column) and node.this.name.lower() == ts_l
    if isinstance(node, (exp.GT, exp.GTE)):
        # value > ts → upper bound on ts
        return isinstance(node.expression, exp.Column) and node.expression.name.lower() == ts_l
    return False


def _is_equality_or_set(node: exp.Expression, ts_col: str) -> bool:
    if isinstance(node, exp.EQ):
        return _references_column(node, ts_col)
    if isinstance(node, exp.In):
        return _references_column(node.this, ts_col)
    return False


# ---- Other checks -------------------------------------------------------------


def _check_select_star(parsed: exp.Expression) -> List[Finding]:
    select = parsed if isinstance(parsed, exp.Select) else parsed.find(exp.Select)
    if select is None:
        return []
    for proj in select.expressions or []:
        if isinstance(proj, exp.Star):
            return [_select_star_finding()]
        # `t.*` is a Column whose `this` is a Star.
        if isinstance(proj, exp.Column) and isinstance(proj.this, exp.Star):
            return [_select_star_finding()]
    return []


def _select_star_finding() -> Finding:
    return Finding(
        code="SELECT_STAR",
        severity="warn",
        message=(
            "`SELECT *` reads every column from columnar storage, multiplying I/O and "
            "result size. Hydrolix tables are wide; this is rarely what you want."
        ),
        suggested_rewrite="Replace `*` with an explicit column list of just what you need.",
    )


def _check_broad_like(parsed: exp.Expression) -> List[Finding]:
    findings: List[Finding] = []
    seen: set[str] = set()
    for node in parsed.find_all(exp.Like):
        pattern = node.expression
        if not isinstance(pattern, exp.Literal) or not pattern.is_string:
            continue
        pat = pattern.this
        if pat.startswith("%") and pat not in seen:
            seen.add(pat)
            findings.append(
                Finding(
                    code="BROAD_LIKE",
                    severity="warn",
                    message=(
                        f"`LIKE {pat!r}` uses a leading wildcard. This forces a full "
                        f"substring scan of the column on every matching row."
                    ),
                    suggested_rewrite=(
                        "If possible, anchor the match: `col LIKE 'prefix%'` or "
                        "`col LIKE '%suffix'` (without internal `%`), or use a more selective filter."
                    ),
                )
            )
    return findings
