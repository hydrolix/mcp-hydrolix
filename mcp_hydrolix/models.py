import dataclasses as _dc
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, List, Optional, TypedDict, Union, get_type_hints

from pydantic import Field, field_serializer
from pydantic.dataclasses import dataclass as pydantic_dataclass


@dataclass(frozen=True)
class Column:
    """A plain dimension column."""

    column_category: ClassVar[str] = "Column"

    name: str
    type: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class AliasColumn:
    """A grouper/dimension alias."""

    column_category: ClassVar[str] = "AliasColumn"

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class AggregateColumn:
    """A column with AggregateFunction or SimpleAggregateFunction type."""

    column_category: ClassVar[str] = "AggregateColumn"

    name: str
    type: str
    base_function: str
    merge_function: str
    comment: Optional[str] = None


@dataclass(frozen=True)
class SummaryColumn:
    """An ALIAS column that transitively depends on aggregate functions."""

    column_category: ClassVar[str] = "SummaryColumn"

    name: str
    type: str
    default_expr: str
    comment: Optional[str] = None


ColumnType = Union[Column, AliasColumn, AggregateColumn, SummaryColumn]


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

    @field_serializer("columns")
    def serialize_columns(self, columns: Optional[List[ColumnType]]) -> List[dict]:
        return [
            {**_dc.asdict(col), "column_category": type(col).column_category}
            for col in (columns or [])
        ]

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
