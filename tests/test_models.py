"""Unit tests for Table serialization — null/empty field filtering."""

from pydantic import TypeAdapter

from mcp_hydrolix.models import AggregateColumn, AliasColumn, Column, SummaryColumn, Table

_table_adapter = TypeAdapter(Table)


def _serialize(table: Table) -> dict:
    """Serialize a Table by running it through Pydantic's serializers.

    This tests our field_serializer/model_serializer logic directly.  FastMCP
    reaches the same result via pydantic_core.to_jsonable_python (fastmcp/tools/
    base.py::Tool.convert_result), which also invokes Pydantic's serializers.
    If FastMCP ever stops using Pydantic for serialization this helper would need
    to be updated to reflect the new path.
    """
    return _table_adapter.dump_python(table)


def _minimal_table(**overrides) -> Table:
    """Return a Table with sensible defaults; override individual fields as needed."""
    defaults = dict(
        database="db",
        name="t",
        engine="MergeTree",
        sorting_key="",
        primary_key="id",
        total_rows=100,
        total_bytes=None,
        total_bytes_uncompressed=None,
        parts=None,
        active_parts=None,
        columns=[],
        is_summary_table=False,
        summary_table_info=None,
    )
    defaults.update(overrides)
    return Table(**defaults)


class TestColumnNullFiltering:
    """Null/empty values are stripped from serialized column dicts."""

    def test_null_comment_omitted(self):
        # Given: a Column with no comment
        col = Column(name="x", type="String", comment=None)
        # When: the table is serialized
        result = _serialize(_minimal_table(columns=[col]))
        # Then: comment is absent from the column dict
        assert "comment" not in result["columns"][0]

    def test_non_null_comment_kept(self):
        # Given: a Column with a comment
        col = Column(name="x", type="String", comment="a description")
        # When: the table is serialized
        result = _serialize(_minimal_table(columns=[col]))
        # Then: comment is present in the column dict
        assert result["columns"][0]["comment"] == "a description"

    def test_required_fields_always_present(self):
        # Given: a plain Column
        col = Column(name="x", type="String")
        # When: the table is serialized
        result = _serialize(_minimal_table(columns=[col]))
        # Then: name, type, and column_category are always present
        col_dict = result["columns"][0]
        assert col_dict["name"] == "x"
        assert col_dict["type"] == "String"
        assert col_dict["column_category"] == "Column"

    def test_aggregate_column_required_fields_present(self):
        # Given: an AggregateColumn with base and merge functions
        col = AggregateColumn(
            name="cnt",
            type="AggregateFunction(count, String)",
            base_function="count",
            merge_function="countMerge",
        )
        # When: the table is serialized
        result = _serialize(_minimal_table(columns=[col]))
        # Then: base_function, merge_function, and column_category are present
        col_dict = result["columns"][0]
        assert col_dict["base_function"] == "count"
        assert col_dict["merge_function"] == "countMerge"
        assert col_dict["column_category"] == "AggregateColumn"

    def test_alias_column_null_comment_omitted(self):
        # Given: an AliasColumn with no comment
        col = AliasColumn(
            name="full_name", type="String", default_expr="concat(a, b)", comment=None
        )
        # When: the table is serialized
        result = _serialize(_minimal_table(columns=[col]))
        # Then: comment is absent and default_expr is present
        col_dict = result["columns"][0]
        assert "comment" not in col_dict
        assert col_dict["default_expr"] == "concat(a, b)"

    def test_summary_column_null_comment_omitted(self):
        # Given: a SummaryColumn with no comment
        col = SummaryColumn(
            name="cnt_all", type="UInt64", default_expr="countMerge(`count()`)", comment=None
        )
        # When: the table is serialized
        result = _serialize(_minimal_table(columns=[col]))
        # Then: comment is absent and default_expr is present
        col_dict = result["columns"][0]
        assert "comment" not in col_dict
        assert col_dict["default_expr"] == "countMerge(`count()`)"


class TestTableNullFiltering:
    """Null/empty values are stripped from serialized Table-level fields."""

    def test_null_size_fields_omitted(self):
        # Given: a table with unknown byte sizes
        table = _minimal_table(total_bytes=None, total_bytes_uncompressed=None)
        # When: the table is serialized
        result = _serialize(table)
        # Then: null size fields are absent
        assert "total_bytes" not in result
        assert "total_bytes_uncompressed" not in result

    def test_null_parts_fields_omitted(self):
        # Given: a table with unknown part counts
        table = _minimal_table(parts=None, active_parts=None)
        # When: the table is serialized
        result = _serialize(table)
        # Then: null parts fields are absent
        assert "parts" not in result
        assert "active_parts" not in result

    def test_empty_sorting_key_omitted(self):
        # Given: a table with no sorting key
        table = _minimal_table(sorting_key="")
        # When: the table is serialized
        result = _serialize(table)
        # Then: empty sorting_key is absent
        assert "sorting_key" not in result

    def test_null_summary_table_info_omitted(self):
        # Given: a non-summary table with no usage guide
        table = _minimal_table(summary_table_info=None)
        # When: the table is serialized
        result = _serialize(table)
        # Then: null summary_table_info is absent
        assert "summary_table_info" not in result

    def test_non_null_fields_preserved(self):
        # Given: a table with meaningful values for optional fields
        table = _minimal_table(
            total_bytes=1024,
            sorting_key="timestamp",
            summary_table_info="use merge functions",
        )
        # When: the table is serialized
        result = _serialize(table)
        # Then: all non-null fields are present
        assert result["total_bytes"] == 1024
        assert result["sorting_key"] == "timestamp"
        assert result["summary_table_info"] == "use merge functions"

    def test_false_is_summary_table_preserved(self):
        # Given: a non-summary table (is_summary_table=False)
        table = _minimal_table(is_summary_table=False)
        # When: the table is serialized
        result = _serialize(table)
        # Then: False is preserved — it is meaningful, not null/empty
        assert "is_summary_table" in result
        assert result["is_summary_table"] is False

    def test_zero_total_rows_preserved(self):
        # Given: a table with zero rows
        table = _minimal_table(total_rows=0)
        # When: the table is serialized
        result = _serialize(table)
        # Then: 0 is preserved — it is meaningful, not null/empty
        assert result["total_rows"] == 0

    def test_empty_columns_list_preserved(self):
        # Given: a table with no columns (e.g. from list_tables which skips column metadata)
        table = _minimal_table(columns=[])
        # When: the table is serialized
        result = _serialize(table)
        # Then: the columns key is present as an empty list, not absent
        assert "columns" in result
        assert result["columns"] == []
