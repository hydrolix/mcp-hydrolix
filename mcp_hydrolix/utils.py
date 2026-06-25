import ipaddress
import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Iterable, List

import sqlglot
import sqlglot.errors as sqlglot_errors
import sqlglot.expressions as exp

logger = logging.getLogger(__name__)


def coerce_cell(v: Any) -> Any:
    """Coerce ClickHouse-specific Python types in a result cell to JSON-friendly
    equivalents.

    `null` values pass through unchanged — `None` in a query result is data
    (the user's SELECT may legitimately return SQL NULLs) and must be preserved.
    """
    if isinstance(v, ipaddress.IPv4Address):
        return str(v)
    if isinstance(v, datetime):
        return v.timestamp()
    if isinstance(v, (date, time)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode()
    if isinstance(v, Decimal):
        return str(v)
    return v


def coerce_rows(rows: List[List[Any]]) -> List[List[Any]]:
    """Apply `coerce_cell` to every cell in a 2D result set."""
    return [[coerce_cell(c) for c in row] for row in rows]


def inject_limit(query: str, max_rows: int) -> str:
    """Rewrite query to enforce a row limit, taking the minimum of any existing LIMIT.

    Returns the rewritten SQL string. If the query cannot be parsed by sqlglot, logs a
    warning and returns the original query unchanged so the caller still executes something.
    """
    try:
        ast = sqlglot.parse_one(query, dialect="clickhouse")
    except sqlglot_errors.SqlglotError:
        logger.warning(
            "inject_limit: could not parse query with sqlglot; LIMIT will not be injected. "
            "Result set may be larger than max_rows=%d.",
            max_rows,
        )
        return query

    existing = ast.args.get("limit")
    if existing:
        try:
            current = int(existing.args["expression"].this)
            existing.set("expression", exp.Literal.number(min(current, max_rows)))
        except (TypeError, ValueError, AttributeError):
            logger.warning(
                "inject_limit: existing LIMIT is a non-literal expression; "
                "leaving it unchanged. Result set may exceed max_rows=%d.",
                max_rows,
            )
    else:
        ast.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
    return ast.sql(dialect="clickhouse")


def strip_conflicting_settings(query: str, protected_keys: Iterable[str]) -> str:
    """Remove inline ``SETTINGS`` entries from the query text that collide with our
    transport-level (guardrail) settings.

    Hydrolix's HTTP query path currently gives the inline ``SETTINGS`` clause in the
    query text *higher* precedence than the transport-level settings we send (the
    ``settings`` dict in :func:`execute_query`). That lets a caller override our
    guardrails (e.g. ``SETTINGS readonly=0``). Until the query head inverts that
    precedence (see HDX-11717), we strip any inline setting whose key matches one we
    declare, so our guardrail value wins de facto.

    We only *delete* conflicting keys — we never synthesise a new ``SETTINGS`` clause,
    because inline settings have ambiguous semantics across nested subqueries (HDX-11548).
    Non-conflicting inline settings (e.g. ``max_threads``) are preserved. Stripping is
    applied to every ``SETTINGS`` clause in the AST (including subqueries) and key
    matching is case-insensitive.

    Returns the rewritten SQL string. If the query cannot be parsed by sqlglot, logs a
    warning and returns the original query unchanged so the caller still executes something.
    """
    protected = {k.lower() for k in protected_keys}
    if not protected:
        return query

    # Fast path: if the query text has no SETTINGS clause at all, there is nothing to
    # strip. Returning it verbatim avoids an unnecessary sqlglot round-trip, which would
    # otherwise re-serialise (and subtly alter) every query — e.g. injecting a space into
    # ClickHouse parameter placeholders like `{db:Identifier}`.
    if "settings" not in query.lower():
        return query

    try:
        ast = sqlglot.parse_one(query, dialect="clickhouse")
    except sqlglot_errors.SqlglotError:
        logger.warning(
            "strip_conflicting_settings: could not parse query with sqlglot; inline "
            "SETTINGS will not be stripped and may override transport-level guardrails."
        )
        return query

    stripped: List[str] = []
    for node in ast.walk():
        settings = node.args.get("settings")
        if not settings:
            continue
        kept = []
        for entry in settings:
            # Each entry is normally an EQ node: <identifier> = <literal>.
            key = entry.this.name if isinstance(entry, exp.EQ) else None
            if key and key.lower() in protected:
                stripped.append(key)
                continue
            kept.append(entry)
        # Set to None (not []) when empty so no dangling `SETTINGS` clause is rendered.
        node.set("settings", kept or None)

    # Nothing conflicted (e.g. the query's SETTINGS are all caller-tunable). Return the
    # original text untouched rather than sqlglot's re-serialised form, so we never alter
    # a query we had no reason to rewrite.
    if not stripped:
        return query

    logger.warning(
        "strip_conflicting_settings: removed inline SETTINGS %s that conflicted with "
        "transport-level guardrails.",
        stripped,
    )
    return ast.sql(dialect="clickhouse")
