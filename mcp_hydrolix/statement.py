"""Text-level handling of user-supplied SQL before it reaches the driver (HDX-12410).

clickhouse-connect appends ``FORMAT Native`` to every non-insert query
(``clickhouse_connect/driver/httpclient.py``, ``HttpClient._prep_query``), so a
FORMAT clause the agent left in produces two FORMAT clauses and the cluster
refuses the statement with code 62. A trailing semicolon followed by the
driver's clause is refused as a multi-statement. Both are removed here.

The scanner follows ClickHouse's lexer: ``--``, ``#`` and ``#!`` start line
comments, block comments nest, single-quoted strings honour backslash escapes,
backtick and double-quoted identifiers are opaque, and a keyword directly after
``identifier.`` or ``AS`` is itself an identifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class Token:
    kind: str  # word | number | literal | quoted | semicolon | paren | punct
    text: str
    start: int
    end: int
    depth: int
    is_identifier: bool


_IDENTIFIER_KINDS: Final[frozenset[str]] = frozenset({"word", "quoted"})


def tokenize(sql: str) -> list[Token]:
    """Split SQL into significant elements, dropping comments.

    String literals and quoted identifiers are emitted whole, so a keyword inside
    one cannot be mistaken for a clause and the end of the statement is known even
    when a literal closes it. Parenthesis depth is recorded on every token.
    """
    tokens: list[Token] = []
    depth = 0
    i = 0
    n = len(sql)

    def emit(kind: str, start: int, end: int) -> None:
        previous = tokens[-1] if tokens else None
        before_previous = tokens[-2] if len(tokens) >= 2 else None
        is_identifier = (
            kind == "word"
            and previous is not None
            and (
                (
                    previous.kind == "punct"
                    and previous.text == "."
                    and before_previous is not None
                    and before_previous.kind in _IDENTIFIER_KINDS
                )
                or (previous.kind == "word" and previous.text.upper() == "AS")
            )
        )
        tokens.append(Token(kind, sql[start:end], start, end, depth, is_identifier))

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if (ch == "-" and nxt == "-") or ch == "#":
            i += 2 if ch == "-" else 1
            while i < n and sql[i] != "\n":
                i += 1
            continue
        if ch == "/" and nxt == "*":
            nesting = 1
            i += 2
            while i < n and nesting:
                if sql.startswith("/*", i):
                    nesting += 1
                    i += 2
                elif sql.startswith("*/", i):
                    nesting -= 1
                    i += 2
                else:
                    i += 1
            continue
        if ch == "'":
            start = i
            i += 1
            while i < n and sql[i] != "'":
                i += 2 if sql[i] == "\\" else 1
            i = min(i + 1, n)
            emit("literal", start, i)
            continue
        if ch in ("`", '"'):
            start = i
            i += 1
            while i < n and sql[i] != ch:
                i += 2 if sql[i] == "\\" else 1
            i = min(i + 1, n)
            emit("quoted", start, i)
            continue
        if ch.isspace():
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            start = i
            while i < n and (sql[i].isalnum() or sql[i] == "_"):
                i += 1
            emit("word", start, i)
            continue
        if ch.isdigit():
            start = i
            while i < n and (sql[i].isalnum() or sql[i] in "._"):
                i += 1
            emit("number", start, i)
            continue
        if ch == "(":
            depth += 1
            emit("paren", i, i + 1)
        elif ch == ")":
            depth = max(0, depth - 1)
            emit("paren", i, i + 1)
        elif ch == ";":
            emit("semicolon", i, i + 1)
        else:
            emit("punct", i, i + 1)
        i += 1
    return tokens


def is_clause_keyword(token: Token, keyword: str) -> bool:
    """True when ``token`` is the top-level clause keyword ``keyword``, not an identifier."""
    return (
        token.kind == "word"
        and not token.is_identifier
        and token.depth == 0
        and token.text.upper() == keyword
    )


@dataclass(frozen=True)
class NormalizedStatement:
    sql: str
    format_removed: bool = False


def normalize_statement(raw_sql: str) -> NormalizedStatement:
    """Trim comments, a trailing semicolon and a trailing top-level ``FORMAT <name>``.

    Inner semicolons are left alone, so multi-statement text reaches the cluster
    exactly as before. Nothing here rewrites the statement's meaning.
    """
    tokens = tokenize(raw_sql)
    if not tokens:
        return NormalizedStatement(sql="")
    end = tokens[-1].end
    if tokens[-1].kind == "semicolon":
        end = tokens[-1].start
        tokens = tokens[:-1]
        if not tokens:
            return NormalizedStatement(sql="")
    sql = raw_sql[tokens[0].start : end].rstrip()
    if len(tokens) >= 2:
        fmt, name = tokens[-2], tokens[-1]
        if is_clause_keyword(fmt, "FORMAT") and name.kind == "word":
            return NormalizedStatement(
                sql=raw_sql[tokens[0].start : fmt.start].rstrip(), format_removed=True
            )
    return NormalizedStatement(sql=sql)
