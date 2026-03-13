"""Unit tests for summary table detection and classification."""

from mcp_hydrolix.mcp_server import (
    AggregateColumn,
    AliasColumn,
    Column,
    SummaryColumn,
    detect_aggregate_aliases,
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


class TestDetectAggregateAliases:
    """Tests for detect_aggregate_aliases - AST-based aggregate alias detection."""

    def test_direct_aggregate_alias(self):
        """Test alias directly wrapping a -Merge function is detected as aggregate."""
        result = detect_aggregate_aliases({"cnt_all": "countMerge(`count()`)"})
        assert "cnt_all" in result

    def test_compound_merge_combinator(self):
        """Test compound -Merge combinators (e.g. countIfMerge) are detected.

        sqlglot does not register countIfMerge as a known AggFunc — it falls back
        to Anonymous.  The _is_agg_node helper catches these via the 'endswith Merge'
        name check so they are not silently misclassified as plain aliases.
        """
        result = detect_aggregate_aliases({"cached_count": "countIfMerge(`countIf(cached)`)"})
        assert "cached_count" in result

    def test_non_aggregate_alias(self):
        """Test alias with no aggregate function is not flagged."""
        result = detect_aggregate_aliases({"full_name": "concat(first_name, ' ', last_name)"})
        assert "full_name" not in result

    def test_transitive_aggregate_alias(self):
        """Test alias referencing aggregate aliases is transitively detected."""
        result = detect_aggregate_aliases(
            {
                "cnt_errors": "countMerge(`count(errors)`)",
                "cnt_all": "countMerge(`count()`)",
                "pct_errors": "cnt_errors / cnt_all * 100",  # no Merge, but depends on aggregates
            }
        )
        assert "cnt_errors" in result
        assert "cnt_all" in result
        assert "pct_errors" in result

    def test_empty_aliases(self):
        """Test empty input returns empty set."""
        assert detect_aggregate_aliases({}) == set()

    def test_non_transitive_alias_not_flagged(self):
        """Test alias referencing only non-aggregate aliases is not flagged."""
        result = detect_aggregate_aliases(
            {
                "full_name": "concat(first_name, ' ', last_name)",
                "upper_name": "upper(full_name)",  # depends on full_name, which is not aggregate
            }
        )
        assert "full_name" not in result
        assert "upper_name" not in result


class TestEnrichColumnMetadata:
    """Tests for enrich_column_metadata - DESCRIBE TABLE row classification."""

    def test_plain_column(self):
        """Test plain column without default type is classified as Column."""
        rows = [
            {
                "name": "vendor_id",
                "type": "String",
                "default_type": "",
                "default_expression": "",
                "comment": "",
            }
        ]
        result = enrich_column_metadata(rows)
        assert isinstance(result[0], Column)
        assert result[0].name == "vendor_id"
        assert result[0].type == "String"

    def test_aggregate_column_from_type(self):
        """Test AggregateFunction type is detected and merge_function populated."""
        rows = [
            {
                "name": "cnt",
                "type": "AggregateFunction(count, String)",
                "default_type": "",
                "default_expression": "",
                "comment": "",
            }
        ]
        result = enrich_column_metadata(rows)
        col = result[0]
        assert isinstance(col, AggregateColumn)
        assert col.base_function == "count"
        assert col.merge_function == "countMerge"

    def test_alias_column(self):
        """Test ALIAS column without aggregate expression is classified as AliasColumn."""
        rows = [
            {
                "name": "full_name",
                "type": "String",
                "default_type": "ALIAS",
                "default_expression": "concat(first, last)",
                "comment": "",
            }
        ]
        result = enrich_column_metadata(rows)
        col = result[0]
        assert isinstance(col, AliasColumn)
        assert col.default_expr == "concat(first, last)"

    def test_summary_column(self):
        """Test ALIAS column wrapping a -Merge function is classified as SummaryColumn."""
        rows = [
            {
                "name": "cnt_all",
                "type": "UInt64",
                "default_type": "ALIAS",
                "default_expression": "countMerge(`count()`)",
                "comment": "",
            }
        ]
        result = enrich_column_metadata(rows)
        assert isinstance(result[0], SummaryColumn)

    def test_transitive_summary_column(self):
        """Test ALIAS column transitively depending on aggregates is classified as SummaryColumn."""
        rows = [
            {
                "name": "cnt_errors",
                "type": "UInt64",
                "default_type": "ALIAS",
                "default_expression": "countMerge(`count(errors)`)",
                "comment": "",
            },
            {
                "name": "cnt_all",
                "type": "UInt64",
                "default_type": "ALIAS",
                "default_expression": "countMerge(`count()`)",
                "comment": "",
            },
            {
                "name": "pct_errors",
                "type": "Float64",
                "default_type": "ALIAS",
                "default_expression": "cnt_errors / cnt_all * 100",
                "comment": "",
            },
        ]
        by_name = {c.name: c for c in enrich_column_metadata(rows)}
        assert isinstance(by_name["cnt_errors"], SummaryColumn)
        assert isinstance(by_name["cnt_all"], SummaryColumn)
        assert isinstance(by_name["pct_errors"], SummaryColumn)

    def test_column_types(self):
        """Test each column kind maps to the correct dataclass type."""
        rows = [
            {
                "name": "vendor_id",
                "type": "String",
                "default_type": "",
                "default_expression": "",
                "comment": "",
            },
            {
                "name": "cnt",
                "type": "AggregateFunction(count, String)",
                "default_type": "",
                "default_expression": "",
                "comment": "",
            },
            {
                "name": "full_name",
                "type": "String",
                "default_type": "ALIAS",
                "default_expression": "concat(a, b)",
                "comment": "",
            },
            {
                "name": "cnt_all",
                "type": "UInt64",
                "default_type": "ALIAS",
                "default_expression": "countMerge(`count()`)",
                "comment": "",
            },
        ]
        by_name = {c.name: c for c in enrich_column_metadata(rows)}
        assert isinstance(by_name["vendor_id"], Column)
        assert isinstance(by_name["cnt"], AggregateColumn)
        assert isinstance(by_name["full_name"], AliasColumn)
        assert isinstance(by_name["cnt_all"], SummaryColumn)
