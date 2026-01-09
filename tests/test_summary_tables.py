"""Unit tests for summary table detection and classification."""

from mcp_hydrolix.mcp_server import (
    Column,
    classify_table_columns,
    enrich_column_metadata,
    extract_function_from_type,
    get_merge_function,
)


class TestExtractFunctionFromType:
    """Tests for extract_function_from_type function (type-based detection)."""

    def test_extracts_function_name(self):
        """Test extraction of function names from AggregateFunction types."""
        # Simple function
        assert extract_function_from_type("AggregateFunction(count, String)") == "count"
        # SimpleAggregateFunction variant
        assert extract_function_from_type("SimpleAggregateFunction(sum, Float64)") == "sum"
        # Parameterized function with single parameter
        assert (
            extract_function_from_type("AggregateFunction(quantile(0.5), Float64)")
            == "quantile(0.5)"
        )
        # Parameterized function with multiple parameters
        assert (
            extract_function_from_type("AggregateFunction(quantile(0.5, 0.9), Float64)")
            == "quantile(0.5, 0.9)"
        )

    def test_returns_none_for_non_aggregates(self):
        """Test that non-aggregate types return None."""
        assert extract_function_from_type("String") is None


class TestGetMergeFunction:
    """Tests for get_merge_function function."""

    def test_adds_merge_suffix(self):
        """Test -Merge suffix is correctly added to function names."""
        assert get_merge_function("count") == "countMerge"

    def test_parameterized_functions_params_after_merge(self):
        """Test parameterized functions - params go AFTER Merge."""
        assert get_merge_function("quantile(0.5)") == "quantileMerge(0.5)"
        assert get_merge_function("quantile(0.5, 0.9)") == "quantileMerge(0.5, 0.9)"


class TestEnrichColumnMetadata:
    """Tests for enrich_column_metadata function."""

    def test_detects_aggregate_from_type(self):
        """Test aggregate columns are detected from AggregateFunction type."""
        col = Column(
            database="test_db",
            table="test_table",
            name="any_name",
            column_type="AggregateFunction(count, String)",
            default_kind="",
            default_expression="",
            comment="",
        )

        enriched = enrich_column_metadata(col)

        assert enriched.column_category == "aggregate"
        assert enriched.base_function == "count"
        assert enriched.merge_function == "countMerge"

    def test_classifies_as_dimension_without_aggregate_type(self):
        """Test columns without AggregateFunction type are dimensions."""
        col = Column(
            database="test_db",
            table="test_table",
            name="vendor_id",
            column_type="String",
            default_kind="",
            default_expression="",
            comment="",
        )

        enriched = enrich_column_metadata(col)

        assert enriched.column_category == "dimension"
        assert enriched.base_function is None
        assert enriched.merge_function is None

    def test_detects_alias_aggregates(self):
        """Test ALIAS columns with -Merge functions are detected."""
        col = Column(
            database="test_db",
            table="test_table",
            name="cnt_all",
            column_type="",
            default_kind="ALIAS",
            default_expression="countMerge(`count()`)",
            comment="",
        )

        enriched = enrich_column_metadata(col)

        assert enriched.column_category == "alias_aggregate"
        assert enriched.base_function is None
        assert enriched.merge_function is None

    def test_alias_without_merge_is_dimension(self):
        """Test ALIAS columns without -Merge are dimensions."""
        col = Column(
            database="test_db",
            table="test_table",
            name="full_name",
            column_type="",
            default_kind="ALIAS",
            default_expression="concat(first_name, ' ', last_name)",
            comment="",
        )

        enriched = enrich_column_metadata(col)

        assert enriched.column_category == "dimension"
        assert enriched.base_function is None
        assert enriched.merge_function is None


class TestClassifyTableColumns:
    """Tests for classify_table_columns function."""

    def test_table_with_aggregates_is_summary_table(self):
        """Test table with aggregate columns is classified as summary table."""
        columns = [
            enrich_column_metadata(
                Column(
                    database="test_db",
                    table="test",
                    name="count(vendor_id)",
                    column_type="AggregateFunction(count, String)",
                    default_kind="",
                    default_expression="",
                    comment="",
                )
            ),
            enrich_column_metadata(
                Column(
                    database="test_db",
                    table="test",
                    name="cdn",
                    column_type="String",
                    default_kind="",
                    default_expression="",
                    comment="",
                )
            ),
        ]

        result = classify_table_columns(columns)

        assert result.is_summary_table is True
        assert len(result.aggregate_columns) == 1
        assert len(result.dimension_columns) == 1

    def test_table_without_aggregates_is_regular_table(self):
        """Test table with only dimensions is not a summary table."""
        columns = [
            enrich_column_metadata(
                Column(
                    database="test_db",
                    table="test",
                    name="vendor_id",
                    column_type="String",
                    default_kind="",
                    default_expression="",
                    comment="",
                )
            ),
        ]

        result = classify_table_columns(columns)

        assert result.is_summary_table is False
        assert len(result.aggregate_columns) == 0
        assert len(result.dimension_columns) == 1
