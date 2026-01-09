# Handling Hydrolix Summary Table Queries in MCP Server

* Status: proposed
* Deciders: [to be filled]
* Date: 2026-01-08

Technical Story: MCP server cannot execute direct SELECT queries on Hydrolix summary tables due to AggregateFunction deserialization issues. This ADR evaluates two technical solutions: (1) automatic query rewriting to inject `-Merge` functions, or (2) native deserialization of binary aggregate states.

## Context and Problem Statement

The MCP Hydrolix server fails when executing direct SELECT queries on summary tables (e.g., `visordb.cdnlogs_summary`) with the error: `AggregateFunction(count) deserialization not supported`.

Summary tables in Hydrolix store pre-computed aggregations using ClickHouse's aggregate function states, which are stored as binary data. While the native ClickHouse client handles these transparently, the MCP server's Python-based ClickHouse client cannot deserialize these aggregate function states.

This creates a significant gap between MCP server and ClickHouse client behavior:
- Native ClickHouse client: `SELECT * FROM cdnlogs_summary LIMIT 10` works fine
- MCP server: Same query fails with deserialization error

Currently, LLMs using the MCP server must generate complex queries with `-Merge` functions:
```sql
SELECT
    cdn,
    countMerge(`count()`) as total_requests,
    sumMerge(`sum(bytes_out)`) as total_bytes
FROM (
    SELECT cdn, `count()`, `sum(bytes_out)`
    FROM visordb.cdnlogs_summary
    WHERE cdn IS NOT NULL
    LIMIT 50000
)
GROUP BY cdn
ORDER BY total_requests DESC;
```

This significantly impacts LLM query generation, requiring queries 5-10x longer and specialized knowledge of MCP-specific workarounds not present in standard ClickHouse documentation.

## Decision Drivers

* **LLM Query Generation**: LLMs should be able to generate correct queries without needing special knowledge of MCP-specific workarounds
* **Consistency**: Behavior should match native ClickHouse client where possible (LLMs are trained on standard ClickHouse patterns)
* **Reliability**: Solution must work consistently across all summary tables and aggregate function types, minimizing LLM query generation errors
* **Maintenance**: Solution should be maintainable and not require constant updates
* **Performance**: Summary tables exist to improve query performance; solution shouldn't negate this

## Considered Options

1. **Query Rewriting Approach** - Automatically detect summary tables and inject `-Merge` functions
2. **Deserialization Approach** - Implement native deserialization of `AggregateFunction` types

## Decision Outcome

Chosen option: **[TO BE DECIDED]**

### Positive Consequences

[To be filled after decision]

### Negative Consequences

[To be filled after decision]

## Pros and Cons of the Options

### Option 1: Query Rewriting Approach

Automatically detect when a query targets a summary table and rewrite it to use `-Merge` functions before execution.

**Implementation:**
```python
def execute_query(query, database):
    table_name = extract_table_name(query)

    # Get table metadata including detection of summary tables
    # Detection checks for AggregateFunction column types (see Summary Table Detection section)
    table_info = get_table_info(database, table_name)

    # If summary table detected, rewrite query to use -Merge functions
    if table_info['is_summary']:
        query = rewrite_with_merge_functions(query, table_info)

    return clickhouse_client.execute(query)
```

**Example transformation:**
- LLM-generated query: `SELECT * FROM cdnlogs_summary WHERE cdn = 'edgio' LIMIT 10`
- Rewritten query:
```sql
SELECT
    cdn,
    status_code,
    countMerge(`count()`) as `count()`,
    sumMerge(`sum(bytes_out)`) as `sum(bytes_out)`,
    avgMerge(`avg(bytes_out)`) as `avg(bytes_out)`
    -- ... all other aggregate columns
FROM (
    SELECT * FROM cdnlogs_summary WHERE cdn = 'edgio' LIMIT 10000
)
GROUP BY cdn, status_code -- all dimension columns
LIMIT 10
```

* **Good:**
  * Transparent to LLMs - generate simple queries like ClickHouse client
  * Works automatically for all summary tables
  * Easier to implement than binary deserialization
  * Can add safety features (automatic LIMIT guards)
  * Leverages existing ClickHouse `-Merge` functionality
  * One-time implementation effort
  * Maintainable SQL manipulation code

* **Bad:**
  * Requires SQL parsing and rewriting logic
  * Complex queries (JOINs, subqueries, CTEs) may be challenging
  * Might change query semantics in edge cases
  * Need to maintain mapping of aggregate functions to `-Merge` variants
  * May produce less optimal query plans in some cases

* **Neutral:**
  * Adds processing overhead for query analysis
  * Requires understanding of ClickHouse aggregate function types

### Option 2: Deserialization Approach

Implement native deserialization of ClickHouse `AggregateFunction` binary states in the result processing layer.

**Implementation:**
```python
def process_result_column(column):
    if column.type.startswith('AggregateFunction'):
        base_func = extract_function_name(column.type)
        return deserialize_aggregate_state(column.data, base_func)
    return column.data
```

* **Good:**
  * "True" fix at the data layer
  * Queries remain unchanged
  * Closest match to native ClickHouse client behavior
  * No SQL rewriting complexity

* **Bad:**
  * Very complex implementation - need to understand binary formats for each aggregate type
  * Must implement for every aggregate function type: count, sum, avg, uniq, quantiles, etc.
  * Underlying Python ClickHouse library may not support this
  * High maintenance burden - new aggregate types require updates
  * Potential performance overhead from deserialization
  * Risk of bugs in binary format handling

* **Neutral:**
  * Requires deep understanding of ClickHouse internals

## Alternatives Considered and Rejected

The following alternatives were considered but rejected as they don't address the core technical issue:

* **Database Views** - Requires creating and maintaining separate views with pre-applied `-Merge` functions for each summary table. Doesn't scale as the number of summary tables grows and requires LLMs to know which views to query instead of base tables.

* **Better Error Messages** - Improving error messages would guide LLMs to the `-Merge` workaround but doesn't eliminate the complexity of generating correct queries. LLMs would still need specialized knowledge of MCP-specific patterns not present in standard ClickHouse documentation.

* **Status Quo** - Documenting the current `-Merge` pattern requirement as expected behavior. This leaves the MCP server with inconsistent behavior compared to the ClickHouse client (which LLMs are trained on) and maintains significant query generation complexity.

## Summary Table Detection

For both Option 1 and Option 2, the MCP server needs to automatically detect when a table is a summary table requiring special handling.

### Detection Method: Inspect Column Types

Query the table schema and check for `AggregateFunction` column types:

```python
def is_summary_table(database, table):
    # Get table schema from ClickHouse
    schema_query = f"""
    SELECT name, type
    FROM system.columns
    WHERE database = '{database}' AND table = '{table}'
    """

    columns = execute_query(schema_query)

    # Check if any column has AggregateFunction type
    for column in columns:
        if column['type'].startswith('AggregateFunction'):
            return True

    return False
```

**Example columns from cdnlogs_summary (column name → column type):**
```
Column Name                           Column Type
-----------                           -----------
count()                         →     AggregateFunction(count)
sum(bytes_out)                  →     AggregateFunction(sum, UInt64)
avg(bytes_out)                  →     AggregateFunction(avg, Float64)
uniq(user_id)                   →     AggregateFunction(uniq, String)
quantiles(0.9, 0.95, 0.99)(bytes_out) → AggregateFunction(quantiles(0.9, 0.95, 0.99), Float64)
```

The detection checks if `column['type'].startswith('AggregateFunction')`.

**Why this works:**
- Summary tables store aggregate function states in columns with `AggregateFunction` types
- Regular tables use standard types (String, Int64, DateTime, etc.)
- Hydrolix uses TurbineStorage for all tables, so engine type cannot be used for detection
- This method works regardless of table naming conventions

### Implementation with Caching

To avoid repeated schema queries, implement caching:

```python
def get_table_info(database, table):
    """
    Query table schema once and extract all needed information.
    Results should be cached for performance.
    """
    query = f"""
    SELECT
        name,
        type,
        default_kind,
        default_expression
    FROM system.columns
    WHERE database = '{database}' AND table = '{table}'
    """

    columns = execute_query(query)

    aggregate_columns = []
    dimension_columns = []

    for col in columns:
        if col['type'].startswith('AggregateFunction'):
            # Parse: AggregateFunction(count) -> count
            func_name = extract_function_name(col['type'])
            aggregate_columns.append({
                'name': col['name'],
                'type': col['type'],
                'function': func_name,
                'merge_function': f"{func_name}Merge"
            })
        else:
            dimension_columns.append(col['name'])

    return {
        'is_summary': len(aggregate_columns) > 0,
        'aggregate_columns': aggregate_columns,
        'dimension_columns': dimension_columns
    }

class SummaryTableCache:
    """Cache table info to avoid repeated schema queries"""
    def __init__(self):
        self._cache = {}

    def get_table_info(self, database, table):
        key = f"{database}.{table}"

        if key not in self._cache:
            self._cache[key] = get_table_info(database, table)

        return self._cache[key]
```

This approach:
- Uses column type inspection (most reliable)
- Caches results to avoid repeated queries
- Provides all information needed for query rewriting (aggregate vs dimension columns)
- Returns mapping of aggregate functions to their `-Merge` equivalents

### Error Handling Considerations

The detection implementation should handle these edge cases:

* **Table doesn't exist** - System query returns empty result set → fail gracefully with "table not found" error

* **Schema query fails** - Network error, permissions issue, etc. → propagate error with clear message, don't cache failed lookups

* **Table has no columns** - Shouldn't happen in practice → handle gracefully by returning `is_summary=False` with empty column lists

* **Cache invalidation** - Consider TTL-based cache invalidation or invalidate on schema change notifications, balancing performance vs staleness

## Additional Context

### Test Results Summary

Testing revealed the following behavior with summary tables:

**Test 1: Summary table direct SELECT**
```sql
SELECT * FROM visordb.cdnlogs_summary
WHERE `toStartOfMinute(timestamp)` >= '2024-12-01'
LIMIT 5;
```
- Status: Deserialization error
- MCP Result: `AggregateFunction(count) deserialization not supported`
- ClickHouse Client Result: Success, returns data
- Conclusion: MCP-specific limitation

**Test 2: Summary table with -Merge pattern (current workaround)**
```sql
SELECT
    cdn,
    countMerge(`count()`) as total_requests,
    sumMerge(`sum(bytes_out)`) as total_bytes
FROM (
    SELECT cdn, `count()`, `sum(bytes_out)`
    FROM visordb.cdnlogs_summary
    WHERE cdn IS NOT NULL
    LIMIT 50000
)
GROUP BY cdn
ORDER BY total_requests DESC;
```
- Status: Success
- MCP Result: Returns correct aggregated data
- Conclusion: Current workaround is functional but requires complex query generation

---

### Technical Details

#### Aggregate Functions Requiring Support

Common aggregate functions found in Hydrolix summary tables:
- `count()`, `countIf()`
- `sum()`, `sumIf()`
- `avg()`, `avgIf()`
- `min()`, `max()`
- `median()`
- `quantiles()`
- `uniq()`
- `any()`
- `assumeNotNull()`

Each aggregate function has a corresponding `-Merge` combinator:
- `count()` → `countMerge()`
- `sum(x)` → `sumMerge(x)`
- `avg(x)` → `avgMerge(x)`
- etc.

#### Performance Constraint

Solution must preserve the performance benefits of summary tables while improving query generation usability.

---

### Implementation Estimates

#### Complexity Comparison

**Option 1 (Query Rewriting):**
- Estimated complexity: Medium
- Components: SQL parser, query rewriter, schema cache
- Risk: Medium (SQL edge cases)
- Maintenance effort: Low to Medium

**Option 2 (Deserialization):**
- Estimated complexity: High
- Components: Binary deserializer for each aggregate type
- Risk: High (binary format bugs)
- Maintenance effort: High

#### Testability

**Option 1 (Query Rewriting):**
- Unit tests for SQL parsing and rewriting logic
- Easy to create test cases (SQL strings in/out)
- Can test against real ClickHouse with sample summary tables
- Mock schema queries for fast unit tests
- Clear success/failure criteria

**Option 2 (Deserialization):**
- Requires binary test fixtures for each aggregate type
- Harder to generate test data (need actual aggregate states)
- Must test against ClickHouse binary format changes
- More complex debugging when tests fail
- Need comprehensive coverage of all aggregate function types
