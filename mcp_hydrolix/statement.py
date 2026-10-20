"""Text-level handling of user-supplied SQL before it reaches the driver (HDX-12410).

clickhouse-connect appends ``FORMAT Native`` to every non-insert query
(``clickhouse_connect/driver/httpclient.py``, ``HttpClient._prep_query``), so a
FORMAT clause the agent left in produces two FORMAT clauses and the cluster
refuses the statement with code 62. A trailing semicolon followed by the
driver's clause is refused as a multi-statement. Both are removed here.

Tokenizing is sqlglot's: the ClickHouse tokenizer knows the dialect's comment
forms (``--``, ``#``, ``#!`` and nested ``/* */``), string literals and quoted
identifiers, and it needs no grammar, so it also handles summary-table
statements that sqlglot's parser cannot read. Nothing here parses SQL, and a
text the tokenizer cannot read is passed through unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlglot.dialects.clickhouse import ClickHouse
from sqlglot.errors import TokenError
from sqlglot.tokens import Token, TokenType

_BARE_WORD = re.compile(r"[A-Za-z_]\w*")


def tokenize(sql: str) -> list[Token]:
    """sqlglot's ClickHouse tokens for ``sql``; comments ride on tokens, not as tokens."""
    return ClickHouse.Tokenizer().tokenize(sql)


@dataclass(frozen=True)
class NormalizedStatement:
    sql: str
    format_removed: bool = False


def _is_trailing_format(raw_sql: str, keyword: Token, name: Token) -> bool:
    # The format name tokenizes as VAR, JSON, NULL or VALUES depending on the word;
    # what identifies the clause is a FORMAT keyword followed by a bare word.
    return (
        keyword.token_type == TokenType.FORMAT
        and _BARE_WORD.fullmatch(raw_sql[name.start : name.end + 1]) is not None
    )


def normalize_statement(raw_sql: str) -> NormalizedStatement:
    """Trim comments, a trailing semicolon and a trailing top-level ``FORMAT <name>``.

    Inner semicolons are left alone, so multi-statement text reaches the cluster
    exactly as before. Nothing here rewrites the statement's meaning.
    """
    try:
        tokens = tokenize(raw_sql)
    except TokenError:
        return NormalizedStatement(sql=raw_sql.strip())
    if not tokens:
        return NormalizedStatement(sql="")
    if tokens[-1].token_type == TokenType.SEMICOLON:
        tokens = tokens[:-1]
        if not tokens:
            return NormalizedStatement(sql="")
    end = tokens[-1].end + 1
    format_removed = False
    if len(tokens) >= 2 and _is_trailing_format(raw_sql, tokens[-2], tokens[-1]):
        end = tokens[-2].start
        format_removed = True
    return NormalizedStatement(
        sql=raw_sql[tokens[0].start : end].rstrip(), format_removed=format_removed
    )


_VIEW_SUFFIX = re.compile(r"#(\w+)")


def find_unquoted_view(raw_sql: str) -> str | None:
    """The quoted form of the first ``db.table#view`` whose ``#`` would read as a comment.

    sqlglot and ClickHouse both treat ``#`` as a line comment, so an unquoted view
    suffix silently falls away and the base table is queried (HDX-12560). Only a
    ``#`` touching a qualified name counts; ``db.t  # note`` is a comment. Position
    is not checked, so ``alias.col#x`` is rejected too.
    """
    try:
        tokens = tokenize(raw_sql)
    except TokenError:
        return None
    for i in range(2, len(tokens)):
        tok = tokens[i]
        # Keyword-like names (date, json, view, ...) get their own token types, so a
        # bare word is matched on its text rather than a list of types.
        if tokens[i - 1].token_type != TokenType.DOT or not (
            tok.token_type == TokenType.IDENTIFIER or _BARE_WORD.fullmatch(tok.text)
        ):
            continue
        view = _VIEW_SUFFIX.match(raw_sql, tok.end + 1)
        if view is None:
            continue
        project = raw_sql[tokens[i - 2].start : tokens[i - 2].end + 1]
        return f"{project}.`{tok.text}#{view.group(1)}`"
    return None
