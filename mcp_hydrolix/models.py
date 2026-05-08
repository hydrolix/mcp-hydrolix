from typing import (
    Annotated,
    Any,
    List,
    Literal,
    Optional,
    TypedDict,
    Union,
    get_type_hints,
)

from pydantic import Field, model_serializer
from pydantic.dataclasses import dataclass as pydantic_dataclass


def _strip_empty(self, handler) -> dict:
    """Drop None and empty-string fields from the serialized dict (token saver)."""
    return {k: v for k, v in handler(self).items() if v is not None and v != ""}


@pydantic_dataclass(frozen=True)
class Column:
    """A plain dimension column."""

    name: str
    type: str
    comment: Optional[str] = None
    column_category: Literal["Column"] = "Column"

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        return _strip_empty(self, handler)


@pydantic_dataclass(frozen=True)
class AliasColumn:
    """A grouper/dimension alias."""

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None
    column_category: Literal["AliasColumn"] = "AliasColumn"

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        return _strip_empty(self, handler)


@pydantic_dataclass(frozen=True)
class AggregateColumn:
    """A column with AggregateFunction or SimpleAggregateFunction type."""

    name: str
    type: str
    base_function: str
    merge_function: str
    comment: Optional[str] = None
    column_category: Literal["AggregateColumn"] = "AggregateColumn"

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        return _strip_empty(self, handler)


@pydantic_dataclass(frozen=True)
class SummaryColumn:
    """An ALIAS column that transitively depends on aggregate functions."""

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None
    column_category: Literal["SummaryColumn"] = "SummaryColumn"

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        return _strip_empty(self, handler)


ColumnType = Annotated[
    Union[Column, AliasColumn, AggregateColumn, SummaryColumn],
    Field(discriminator="column_category"),
]


class _SystemCol:
    """Marker: this field corresponds to a column in system.tables."""


SystemCol = _SystemCol()


@pydantic_dataclass
class Table:
    """Table with summary table detection (is_summary_table=True if aggregate
    columns are present)."""

    database: Annotated[str, SystemCol]
    name: Annotated[str, SystemCol]
    engine: Annotated[str, SystemCol]
    sorting_key: Annotated[str, SystemCol]
    primary_key: Annotated[str, SystemCol]
    total_rows: Annotated[Optional[int], SystemCol]
    total_bytes: Annotated[Optional[int], SystemCol]
    total_bytes_uncompressed: Annotated[Optional[int], SystemCol]
    parts: Annotated[Optional[int], SystemCol]
    active_parts: Annotated[Optional[int], SystemCol]
    columns: Optional[List[ColumnType]] = Field(default_factory=list)
    is_summary_table: Optional[bool] = None
    summary_table_info: Optional[str] = None

    @model_serializer(mode="wrap")
    def serialize_table(self, handler) -> dict:
        # handler runs Pydantic's default serialization (which now invokes each
        # column type's own _strip_empty serializer) and returns a dict, which
        # we then filter at the table level.
        d = handler(self)
        return {k: v for k, v in d.items() if v is not None and v != ""}

    @classmethod
    def sql_fields(cls) -> List[str]:
        """Comma-separated column names for SELECT from system.tables."""
        hints = get_type_hints(cls, include_extras=True)
        return [
            name
            for name, hint in hints.items()
            if any(isinstance(m, _SystemCol) for m in getattr(hint, "__metadata__", ()))
        ]


class HdxQueryResult(TypedDict):
    columns: List[str]
    rows: List[List[Any]]


@pydantic_dataclass(frozen=True)
class DatabaseList:
    """Result of `list_databases` — wraps a list of database names so the
    structured payload is a JSON object (as MCP requires) with an explicit
    field name instead of fastmcp's generic `result` wrapper."""

    databases: List[str]


@pydantic_dataclass(frozen=True)
class TableList:
    """Result of `list_tables` — wraps a list of tables so the structured
    payload is a JSON object (as MCP requires) with an explicit field name
    instead of fastmcp's generic `result` wrapper."""

    tables: List[Table]


@pydantic_dataclass(frozen=True)
class Finding:
    """One advisory finding from query analysis."""

    code: str
    severity: Literal["info", "warn", "high"]
    message: str
    suggested_rewrite: Optional[str] = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        return _strip_empty(self, handler)


@pydantic_dataclass(frozen=True)
class QueryAnalysis:
    """Result of analyzing a SELECT query for common foot-guns.

    `ok` is True iff no high-severity findings were emitted. `parsed_tables` is
    the sorted set of fully-qualified table names referenced by the query.
    """

    ok: bool
    findings: List[Finding]
    parsed_tables: List[str]


@pydantic_dataclass(frozen=True)
class BadQuery:
    """One row in the find_bad_queries result.

    `exec_time_ms` is the wall-clock execution time the query head observed.
    `analysis` is the static analyzer's verdict on `query`; it is None only
    when the SQL text was missing from the log row.
    """

    query: str
    timestamp: Optional[str] = None
    user: Optional[str] = None
    query_id: Optional[str] = None
    exec_time_ms: Optional[int] = None
    num_partitions: Optional[int] = None
    num_peers: Optional[int] = None
    result_rows: Optional[int] = None
    memory_usage_bytes: Optional[int] = None
    error: Optional[str] = None
    analysis: Optional[QueryAnalysis] = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        return _strip_empty(self, handler)


@pydantic_dataclass(frozen=True)
class BadQueryList:
    """Result of find_bad_queries — wraps the list so MCP receives a JSON object."""

    queries: List[BadQuery]


@pydantic_dataclass(frozen=True)
class RunSelectQueryResult:
    """Stable typed shape for `run_select_query`.

    `total_row_count` and `message` are only meaningful when `truncated=True`;
    they default to None and are stripped from the wire payload by the
    serializer when absent (token saver). Schema still declares them Optional
    so strict clients accept the missing fields.

    `rows` cells are passed through as-is — `null`s inside user query results
    are kept (they may be meaningful data from the user's SELECT).
    """

    columns: List[str]
    rows: List[List[Any]]
    truncated: bool
    row_count: int
    total_row_count: Optional[int] = None
    message: Optional[str] = None

    @model_serializer(mode="wrap")
    def _serialize(self, handler) -> dict:
        return {k: v for k, v in handler(self).items() if v is not None}
