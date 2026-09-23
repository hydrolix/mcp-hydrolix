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
