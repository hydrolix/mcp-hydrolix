"""Read-only SQL preflight for user-supplied queries (HDX-12410).

A port of the console's shared guard (hydrolix-console
``packages/cluster-client/src/utils/queryGuardrails.ts``), so the two MCP
surfaces refuse and rewrite the same statements. It is a statement-shape
guard, not an authorization boundary: what the user may read is decided by the
cluster's own RBAC, and the cluster's ``readonly`` setting still applies.

Deviations from the console scanner, all in the strict direction or fixing a
false positive: a keyword directly after ``.`` is an identifier (``FROM
system.settings`` is a table, not a clause), single-quoted strings honour
backslash escapes, double-quoted identifiers are skipped like backticks, and a
word may contain digits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

READ_STATEMENT_PREFIXES: Final[tuple[str, ...]] = (
    "SELECT",
    "WITH",
    "SHOW",
    "DESC",
    "DESCRIBE",
    "EXPLAIN",
)

# Known write / DDL / session statements. Used only to phrase the block reason;
# the allow-list above is the hard gate, so anything not explicitly a read
# statement is blocked regardless of this set.
_WRITE_OR_DDL: Final[frozenset[str]] = frozenset(
    {
        "INSERT",
        "CREATE",
        "DROP",
        "ALTER",
        "RENAME",
        "ATTACH",
        "DETACH",
        "TRUNCATE",
        "OPTIMIZE",
        "DELETE",
        "UPDATE",
        "GRANT",
        "REVOKE",
        "SET",
        "USE",
        "SYSTEM",
        "KILL",
        "EXCHANGE",
        "MOVE",
        "BACKUP",
        "RESTORE",
        "UNDROP",
        "WATCH",
    }
)

_READ_ONLY_TAIL: Final[str] = (
    "Only SELECT, WITH, SHOW, DESC, DESCRIBE, and EXPLAIN queries can run here."
)
SINGLE_STATEMENT_REASON: Final[str] = "Only single statements are supported."
SETTINGS_CLAUSE_REASON: Final[str] = (
    "A SETTINGS clause is not allowed here; row, byte and time limits are set by the server."
)
EMPTY_QUERY_REASON: Final[str] = "Empty query."


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of :func:`preflight`.

    ``sql`` is the statement to execute (trailing semicolon and FORMAT clause
    removed) when ``blocked`` is False; it is the trimmed input otherwise.
    """

    sql: str
    blocked: bool
    block_reason: Optional[str] = None
    format_removed: bool = False


@dataclass(frozen=True)
class _Token:
    kind: str  # word | semicolon | paren | punct
    text: str
    start: int
    end: int
    depth: int
    after_dot: bool


def _tokenize(sql: str) -> list[_Token]:
    """Split SQL into significant tokens, skipping comments and quoted text.

    Strings and quoted identifiers are consumed whole and never emitted, so a
    keyword inside a literal cannot trip the guard. Parenthesis depth is
    recorded on every token so the caller can tell a top-level clause from one
    inside a subquery.
    """
    tokens: list[_Token] = []
    depth = 0
    prev_was_dot = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if ch == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        if ch == "'":
            i += 1
            while i < n and sql[i] != "'":
                i += 2 if sql[i] == "\\" else 1
            i += 1
            prev_was_dot = False
            continue
        if ch in ("`", '"'):
            end = sql.find(ch, i + 1)
            i = n if end == -1 else end + 1
            prev_was_dot = False
            continue
        if ch.isspace():
            i += 1
            continue

        if ch.isalpha() or ch == "_":
            start = i
            while i < n and (sql[i].isalnum() or sql[i] == "_"):
                i += 1
            tokens.append(_Token("word", sql[start:i], start, i, depth, prev_was_dot))
            prev_was_dot = False
            continue

        if ch == "(":
            depth += 1
            tokens.append(_Token("paren", ch, i, i + 1, depth, False))
        elif ch == ")":
            depth = max(0, depth - 1)
            tokens.append(_Token("paren", ch, i, i + 1, depth, False))
        elif ch == ";":
            tokens.append(_Token("semicolon", ch, i, i + 1, depth, False))
        else:
            tokens.append(_Token("punct", ch, i, i + 1, depth, False))
        prev_was_dot = ch == "."
        i += 1
    return tokens


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _suggest_prefix(word: str) -> Optional[str]:
    best, best_d = None, 3
    for prefix in READ_STATEMENT_PREFIXES:
        d = _edit_distance(word, prefix)
        if d < best_d:
            best, best_d = prefix, d
    return best


def _read_only_block_reason(first_word: Optional[str], surface_name: str) -> str:
    if not first_word:
        return _READ_ONLY_TAIL
    if first_word in _WRITE_OR_DDL:
        return (
            f"This is a read-only {surface_name}: {first_word} statements are not allowed. "
            f"{_READ_ONLY_TAIL}"
        )
    suggestion = _suggest_prefix(first_word)
    hint = f" Did you mean {suggestion}?" if suggestion else ""
    return f'Unrecognized statement "{first_word}".{hint} {_READ_ONLY_TAIL}'


def preflight(raw_sql: str, *, surface_name: str = "query tool") -> PreflightResult:
    """Check one user-supplied statement and normalise it for execution.

    Rules, in order: the statement must be non-empty; it must be a single
    statement (a trailing semicolon is dropped); its first word must be one of
    :data:`READ_STATEMENT_PREFIXES`; it must not carry a top-level ``SETTINGS``
    clause (nested clauses are handled by ``strip_conflicting_settings``); a
    trailing top-level ``FORMAT <name>`` is removed because the client selects
    the wire format itself.
    """
    tokens = _tokenize(raw_sql)
    if not tokens:
        return PreflightResult(sql="", blocked=True, block_reason=EMPTY_QUERY_REASON)

    for index, token in enumerate(tokens):
        if token.kind == "semicolon" and index != len(tokens) - 1:
            return PreflightResult(
                sql=raw_sql.strip(), blocked=True, block_reason=SINGLE_STATEMENT_REASON
            )

    if tokens[-1].kind == "semicolon":
        end = tokens[-1].start
        tokens = tokens[:-1]
        if not tokens:
            return PreflightResult(sql="", blocked=True, block_reason=EMPTY_QUERY_REASON)
    else:
        end = tokens[-1].end
    sql = raw_sql[tokens[0].start : end].rstrip()

    first = tokens[0]
    first_word = first.text.upper() if first.kind == "word" else None
    if first_word not in READ_STATEMENT_PREFIXES:
        return PreflightResult(
            sql=sql, blocked=True, block_reason=_read_only_block_reason(first_word, surface_name)
        )

    for token in tokens:
        if (
            token.kind == "word"
            and token.depth == 0
            and not token.after_dot
            and token.text.upper() == "SETTINGS"
        ):
            return PreflightResult(sql=sql, blocked=True, block_reason=SETTINGS_CLAUSE_REASON)

    format_removed = False
    if len(tokens) >= 2:
        fmt, name = tokens[-2], tokens[-1]
        if (
            fmt.kind == "word"
            and fmt.depth == 0
            and not fmt.after_dot
            and fmt.text.upper() == "FORMAT"
            and name.kind == "word"
        ):
            sql = raw_sql[tokens[0].start : fmt.start].rstrip()
            format_removed = True

    return PreflightResult(sql=sql, blocked=False, format_removed=format_removed)
