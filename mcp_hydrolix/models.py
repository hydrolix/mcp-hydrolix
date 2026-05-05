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
