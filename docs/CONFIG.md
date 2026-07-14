# Configuration Reference

Endpoint overrides, deprecated aliases, and optional tuning variables for the Hydrolix connection. For required connection and authentication variables (`HYDROLIX_URL`, `HYDROLIX_TOKEN`, `HYDROLIX_USER`/`HYDROLIX_PASSWORD`) and per-request authentication with HTTP transport, see [Environment Variables](../README.md#environment-variables) in the main README.

Set these variables in the MCP config block (see [Configuration Example (Claude Desktop)](../README.md#configuration-example-claude-desktop) in the main README), a `.env` file, or the environment directly.

## Endpoint overrides

These override the values derived from `HYDROLIX_URL`. They are useful for in-cluster deployments where the HTTP query endpoint and the version-API live at different internal hostnames or ports. Override precedence: explicit new var > deprecated alias > `HYDROLIX_URL`-derived > hard default.

* `HYDROLIX_HTTP_QUERY_HOST` / `HYDROLIX_HTTP_QUERY_PORT` / `HYDROLIX_HTTP_QUERY_SECURE`: override the ClickHouse HTTP query endpoint.
* `HYDROLIX_HTTP_QUERY_PATH`: override the request path for the ClickHouse HTTP query endpoint (default `/query`, matching Traefik's external routing; set to `/` for in-cluster targets that serve queries at the root).
* `HYDROLIX_VERSION_API_HOST` / `HYDROLIX_VERSION_API_PORT` / `HYDROLIX_VERSION_API_SECURE`: override the REST `/version` probe endpoint. `HYDROLIX_VERSION_API_SECURE` inherits from the resolved HTTP-query secure value by default.

## Deprecated variables

The following are still honored during the transition window but will be removed in a future release. Migrate at your convenience:

| Deprecated | Replacement |
|---|---|
| `HYDROLIX_HOST` | `HYDROLIX_URL` (preferred) or `HYDROLIX_HTTP_QUERY_HOST` |
| `HYDROLIX_PORT` | `HYDROLIX_HTTP_QUERY_PORT` |
| `HYDROLIX_SECURE` | `HYDROLIX_HTTP_QUERY_SECURE` |
| `HYDROLIX_API_HOST` | `HYDROLIX_VERSION_API_HOST` |
| `HYDROLIX_API_PORT` | `HYDROLIX_VERSION_API_PORT` |
| `HYDROLIX_PROXY_PATH` | `HYDROLIX_HTTP_QUERY_PATH` |

External operators using any of these will see a one-time startup warning advising the migration to `HYDROLIX_URL`. In-cluster (o6r-managed) deployments will not see this warning; their migration is handled by the platform.

## Optional Variables
* `HYDROLIX_VERIFY`: Enable/disable SSL certificate verification
  * Default: `"true"`
  * Set to `"false"` to disable certificate verification (not recommended for production)
* `HYDROLIX_CONNECT_TIMEOUT`: Connection timeout in seconds
  * Default: `30`
* `HYDROLIX_SEND_RECEIVE_TIMEOUT`: Send/receive timeout in seconds
  * Default: `300`
* `HYDROLIX_QUERY_TIMEOUT_SECS`: Per-query execution timeout in seconds
  * Default: `30`
* `HYDROLIX_QUERIES_POOL_SIZE`: Size of the client-side query executor thread pool (`executor_threads` passed to clickhouse-connect)
  * Default: `100`
  * Unrelated to `HYDROLIX_QUERY_POOL` / `HYDROLIX_QUERY_HEAD_POOL`, which route queries to cluster-side pools
* `HYDROLIX_MCP_SERVER_TRANSPORT`: Sets the transport method for the MCP server.
  * Default: `"stdio"`
  * Valid options: `"stdio"`, `"http"`, `"sse"`. This is useful for local development with tools like MCP Inspector.
* `HYDROLIX_MCP_BIND_HOST`: Host to bind the MCP server to when using HTTP or SSE transport
  * Default: `"127.0.0.1"`
  * Set to `"0.0.0.0"` to bind to all network interfaces (useful for Docker or remote access)
  * Only used when transport is `"http"` or `"sse"`
* `HYDROLIX_MCP_BIND_PORT`: Port to bind the MCP server to when using HTTP or SSE transport
  * Default: `"8000"`
  * Only used when transport is `"http"` or `"sse"`

### Query SETTINGS overrides

These map to per-query Hydrolix/ClickHouse settings sent with every query:

* `HYDROLIX_QUERY_TIMERANGE_REQUIRED`: Whether SELECT queries must constrain their primary timestamp range (`hdx_query_timerange_required`)
  * Default: `"true"`
  * Only an explicit `"false"` disables the guard; any other value (including a typo) keeps it on
* `HYDROLIX_QUERY_MAX_MEMORY_USAGE`: Max bytes of memory a single query may use (`hdx_query_max_memory_usage`)
  * Default: `2147483648` (2 GiB)
* `HYDROLIX_QUERY_MAX_ATTEMPTS`: Max number of times Hydrolix retries a query (`hdx_query_max_attempts`)
  * Default: `1` (no retries)
* `HYDROLIX_QUERY_MAX_RESULT_ROWS`: Max number of rows a query may return (`hdx_query_max_result_rows`)
  * Default: `100000`

### Result truncation

* `HYDROLIX_MAX_RESULT_CELLS`: Default cell budget (rows × columns) for query result truncation
  * Default: `50000`
* `HYDROLIX_MAX_RESULT_CELLS_LIMIT`: Hard upper bound on the `max_cells` value callers may request; any per-call value above this is capped
  * Default: `0` (no cap enforced)
  * Set to a positive integer in multi-tenant HTTP/SSE deployments to prevent a single session from materializing very large result sets
* `HYDROLIX_MAX_RAW_TIMERANGE`: Maximum time range in seconds allowed for queries against non-summary tables
  * Default: `21600` (6 hours)
  * Queries targeting summary tables are not affected by this limit
* `HYDROLIX_QUERY_POOL`: Name of the Hydrolix query pool to route queries to (sets `hdx_query_pool_name`)
  * Default: None (uses the cluster's default query pool)
  * When set, every query the server issues is routed to the named pool; the pool must already exist on the cluster
  * In platform-managed (in-cluster) deployments the cluster tunable is mapped onto this same variable; the deployment owns the environment, so its value is authoritative
* `HYDROLIX_QUERY_HEAD_POOL`: Name of the Hydrolix query-head pool to route this connection to
  * Default: None (uses the cluster's default query head)
  * Unlike `HYDROLIX_QUERY_POOL` (a per-query setting for the query *peer* pool), query-head pool selection is connection-time routing keyed on the database name: the value is sent as the connection's default database (the `?database=` parameter), which CHProxy matches against the operator-configured routing rules to pick a query-head pool. It is therefore a database name those rules map to a pool, not necessarily a literal pool name
  * The value must name a database that **already exists** on the cluster. Because the routing key doubles as the ClickHouse default database, a non-existent value can cause the query-head to reject the connection
  * Only meaningful when query-head pooling (CHProxy) is enabled on the cluster. If it is not, no routing occurs and the value is simply the connection's default database — harmless when it is a real database (queries are fully qualified `db.table`, so the default is unused for name resolution). Leave this unset on clusters without query-head pooling
* `HYDROLIX_HTTPS_PROXY` / `HYDROLIX_HTTP_PROXY`: Outbound proxy for reaching the Hydrolix cluster
  * Default: None (connect directly)
  * Set one to route the connection through a corporate proxy; include the scheme, e.g. `http://proxy.corp:8080`. If both are set, `HYDROLIX_HTTPS_PROXY` wins
  * The standard `HTTP_PROXY`/`HTTPS_PROXY` environment variables are **not** used — the server needs these explicit `HYDROLIX_`-prefixed vars
  * This is the single egress proxy for all cluster traffic, including the internal `/version` capability probe; the proxy must permit that request, or the server silently falls back to non-parameterized queries
  * Note: this is unrelated to `HYDROLIX_QUERIES_POOL_SIZE`, which sizes the client-side query thread pool
* `HYDROLIX_METRICS_ENABLED`: Enable Prometheus metrics
  * Default: `"false"`

### HTTP/SSE worker tuning

Only used when `HYDROLIX_MCP_SERVER_TRANSPORT` is `"http"` or `"sse"`:

* `HYDROLIX_MCP_WORKERS`: Number of worker processes
  * Default: `1`
* `HYDROLIX_MCP_WORKER_CONNECTIONS`: Max number of concurrent requests per worker
  * Default: `100`
* `HYDROLIX_MCP_REQUEST_TIMEOUT`: Request timeout in seconds
  * Default: `120`
* `HYDROLIX_MCP_MAX_REQUESTS`: Max HTTP requests a worker serves before being gracefully recycled (uvicorn `limit_max_requests`, parallels gunicorn's `max_requests`)
  * Default: `10000`
  * Set to `0` to disable. Only effective with `HYDROLIX_MCP_WORKERS > 1` — single-worker mode has no supervisor to respawn the process
* `HYDROLIX_MCP_MAX_REQUESTS_JITTER`: Random jitter added to `HYDROLIX_MCP_MAX_REQUESTS` per worker, to prevent all workers recycling simultaneously (uvicorn `limit_max_requests_jitter`)
  * Default: `1000`
* `HYDROLIX_MCP_MAX_KEEPALIVE`: Seconds idle keepalive connections are kept alive
  * Default: `10`
* `HYDROLIX_MCP_GRACEFUL_TIMEOUT`: Seconds to wait for in-flight requests during shutdown
  * Default: same as `HYDROLIX_MCP_REQUEST_TIMEOUT`
* `HYDROLIX_MCP_WORKER_HEALTHCHECK_TIMEOUT`: Seconds the supervisor waits for a worker ping response before killing it (uvicorn `timeout_worker_healthcheck`)
  * Default: `15`

### Escape hatches

* `MCP_HYDROLIX_TRUSTSTORE_DISABLE`: Disable injecting the OS trust store into Python's SSL context (note the `MCP_HYDROLIX_` prefix, not `HYDROLIX_`)
  * Default: unset (truststore injection enabled)
  * Set to exactly `"1"` to disable; any other value (including unset) leaves injection enabled


For MCP Inspector or remote access with HTTP transport:

```env
HYDROLIX_URL=https://my-cluster.hydrolix.net
HYDROLIX_USER=default
HYDROLIX_PASSWORD=myPassword
HYDROLIX_MCP_SERVER_TRANSPORT=http
HYDROLIX_MCP_BIND_HOST=0.0.0.0  # Bind to all interfaces
HYDROLIX_MCP_BIND_PORT=4200  # Custom port (default: 8000)
```

When using HTTP transport, the server will run on the configured port (default 8000). For example, with the above configuration:
- MCP endpoint: `http://localhost:4200/mcp`
- Health check: `http://localhost:4200/health`

Note: The bind host and port settings are only used when transport is set to "http" or "sse".

For authentication (including per-request authentication with HTTP transport, and the recommendation to use a Bearer header), see [Environment Variables](../README.md#environment-variables) in the main README.
