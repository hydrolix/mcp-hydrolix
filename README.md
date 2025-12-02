# Hydrolix MCP Server

[![PyPI - Version](https://img.shields.io/pypi/v/mcp-hydrolix)](https://pypi.org/project/mcp-hydrolix)

An MCP server for Hydrolix.

## Tools

* `run_select_query`
  * Execute SQL queries on your Hydrolix cluster.
  * Input: `sql` (string): The SQL query to execute.
  * All Hydrolix queries are run with `readonly = 1` to ensure they are safe.

* `list_databases`
  * List all databases on your Hydrolix cluster.

* `list_tables`
  * List all tables in a database.
  * Input: `database` (string): The name of the database.

## Effective Usage

Due to the wide variety in LLM architectures, not all models will proactively use the tools above, and few will use them effectively without guidance, even with the carefully-constructed tool descriptions provided to the model. To get the best results out of your model while using the Hydrolix MCP server, we recommend the following:

* Refer to your Hydrolix database by name and request tool usage in your prompts (e.g., "Using MCP tools to access my Hydrolix database, please ...")
  - This encourages the model to use the MCP tools available and minimizes hallucinations.
* Include time ranges in your prompts (e.g., "Between December 5 2023 and January 18 2024, ...") and specifically request that the output be ordered by timestamp.
  - This prompts the model to write more efficient queries that take advantage of [primary key optimizations](https://hydrolix.io/blog/optimizing-latest-n-row-queries/)

### Health Check Endpoint

When running with HTTP or SSE transport, a health check endpoint is available at `/health`. This endpoint:
- Returns `200 OK` with the Hydrolix query-head's Clickhouse version if the server is healthy and can connect to Hydrolix
- Returns `503 Service Unavailable` if the server cannot connect to the Hydrolix query-head

Example:
```bash
curl http://localhost:8000/health
# Response: OK - Connected to Hydrolix compatible with ClickHouse 24.3.1
```

## Configuration

The Hydrolix MCP server is configured using a standard MCP server entry. Consult your client's documentation for specific instructions on where to find or declare MCP servers. An example setup using Claude Desktop is documented below.

The recommended way to launch the Hydrolix MCP server is via the [`uv` project manager](https://github.com/astral-sh/uv), which will manage installing all other dependencies in an isolated environment.

### Authentication

The server supports multiple authentication methods with the following precedence (highest to lowest):

1. **Per-request Bearer token**: Service account token provided via `Authorization: Bearer <token>` header
2. **Per-request GET parameter**: Service account token provided via `?token=<token>` query parameter
3. **Environment-based credentials**: Credentials configured via environment variables
   - Service account token (`HYDROLIX_TOKEN`), or
   - Username and password (`HYDROLIX_USER` and `HYDROLIX_PASSWORD`)

When multiple authentication methods are configured, the server will use the first available method in the precedence order above. Per-request authentication is only available when using HTTP or SSE transport modes.

MCP Server definition using username and password (JSON):

```json
{
  "command": "uv",
  "args": [
    "run",
    "--with",
    "mcp-hydrolix",
    "--python",
    "3.13",
    "mcp-hydrolix"
  ],
  "env": {
    "HYDROLIX_HOST": "<hydrolix-host>",
    "HYDROLIX_USER": "<hydrolix-user>",
    "HYDROLIX_PASSWORD": "<hydrolix-password>"
  }
}
```

MCP Server definition using service account token (JSON):

```json
{
  "command": "uv",
  "args": [
    "run",
    "--with",
    "mcp-hydrolix",
    "--python",
    "3.13",
    "mcp-hydrolix"
  ],
  "env": {
    "HYDROLIX_HOST": "<hydrolix-host>",
    "HYDROLIX_TOKEN": "<hydrolix-service-account-token>"
  }
}
```

MCP Server definition using username and password (YAML):

```yaml
command: uv
args:
- run
- --with
- mcp-hydrolix
- --python
- "3.13"
- mcp-hydrolix
env:
  HYDROLIX_HOST: <hydrolix-host>
  HYDROLIX_USER: <hydrolix-user>
  HYDROLIX_PASSWORD: <hydrolix-password>
```

MCP Server definition using service account token (YAML):

```yaml
command: uv
args:
- run
- --with
- mcp-hydrolix
- --python
- "3.13"
- mcp-hydrolix
env:
  HYDROLIX_HOST: <hydrolix-host>
  HYDROLIX_TOKEN: <hydrolix-service-account-token>
```

### Configuration Example (Claude Desktop)

1. Open the Claude Desktop configuration file located at:
   - On macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

2. Add a `mcp-hydrolix` server entry to the `mcpServers` config block to use username and password:

```json
{
  "mcpServers": {
    "mcp-hydrolix": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp-hydrolix",
        "--python",
        "3.13",
        "mcp-hydrolix"
      ],
      "env": {
        "HYDROLIX_HOST": "<hydrolix-host>",
        "HYDROLIX_USER": "<hydrolix-user>",
        "HYDROLIX_PASSWORD": "<hydrolix-password>"
      }
    }
  }
}
```

To leverage service account use the following config block:

```json
{
  "mcpServers": {
    "mcp-hydrolix": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp-hydrolix",
        "--python",
        "3.13",
        "mcp-hydrolix"
      ],
      "env": {
        "HYDROLIX_HOST": "<hydrolix-host>",
        "HYDROLIX_TOKEN": "<hydrolix-service-account-token>"
      }
    }
  }
}
```

3. Update the environment variable definitions to point to your Hydrolix cluster.

4. (Recommended) Locate the command entry for `uv` and replace it with the absolute path to the `uv` executable. This ensures that the correct version of `uv` is used when starting the server. You can find this path using `which uv` or `where.exe uv`.

5. Restart Claude Desktop to apply the changes. If you are using Windows, ensure Claude is stopped completely by closing the client using the system tray icon.

### Configuration Example (Claude Code)

To configure the Hydrolix MCP server for Claude Code, run the following command:

```bash
claude mcp add --transport stdio hydrolix \
  --env HYDROLIX_USER=<hydrolix-user> \
  --env HYDROLIX_PASSWORD=<hydrolix-password> \
  --env HYDROLIX_HOST=<hydrolix-host> \
  --env HYDROLIX_MCP_SERVER_TRANSPORT=stdio \
  -- uv run --with mcp-hydrolix --python 3.13 mcp-hydrolix
```

### Environment Variables

The following variables are used to configure the Hydrolix connection. These variables may be provided via the MCP config block (as shown above), a `.env` file, or traditional environment variables.

#### Required Variables
* `HYDROLIX_HOST`: The hostname of your Hydrolix server

#### Authentication Variables
At least one authentication method must be configured when using the stdio transport:

* `HYDROLIX_TOKEN`: Service account token for environment-based authentication
* `HYDROLIX_USER` and `HYDROLIX_PASSWORD`: Username and password for environment-based authentication (both must be provided together)

In summary:
- For stdio, you MUST use HYDROLIX_TOKEN or HYDROLIX_USER+HYDROLIX_PASS (environmental credentials)
- For http/sse, you MAY use HYDROLIX_TOKEN or HYDROLIX_USER+HYDROLIX_PASS (environmental credentials), but you may instead use per-request credentials.

If no credentials are provided via the environment or the request, the request will fail.

#### Optional Variables
* `HYDROLIX_PORT`: The port number of your Hydrolix server
  * Default: `8088`
  * Usually doesn't need to be set unless using a non-standard port
* `HYDROLIX_VERIFY`: Enable/disable SSL certificate verification
  * Default: `"true"`
  * Set to `"false"` to disable certificate verification (not recommended for production)
* `HYDROLIX_DATABASE`: Default database to use
  *Default: None (uses server default)
  * Set this to automatically connect to a specific database
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


For MCP Inspector or remote access with HTTP transport:

```env
HYDROLIX_HOST=localhost
HYDROLIX_USER=default
HYDROLIX_PASSWORD=myPassword
HYDROLIX_MCP_SERVER_TRANSPORT=http
HYDROLIX_MCP_BIND_HOST=0.0.0.0  # Bind to all interfaces
HYDROLIX_MCP_BIND_PORT=4200  # Custom port (default: 8000)
```

When using HTTP transport, the server will run on the configured port (default 8000). For example, with the above configuration:
- MCP endpoint: `http://localhost:4200/mcp`
- Health check: `http://localhost:4200/health`

#### Using Per-Request Authentication with HTTP Transport

When using HTTP or SSE transport, you can omit environment-based credentials and instead provide authentication per-request. This is useful for multi-user scenarios or with clients that don't support running MCP servers locally.

Example `mcpServers` configuration connecting to a remote HTTP server with per-request authentication:

```json
{
  "mcpServers": {
    "mcp-hydrolix-remote": {
      "url": "http://my-hydrolix-mcp.example.com:8000/mcp?token=<service-account-token>"
    }
  }
}
```

Example minimal `.env` configuration for running your own HTTP server without environment credentials:

```env
HYDROLIX_HOST=my-cluster.hydrolix.net
HYDROLIX_MCP_SERVER_TRANSPORT=http
```

Though not part of the MCP specification, many MCP clients allow adding headers to MCP-issued requests. When this is possible, we recommend configuring the MCP client to pass a service account token via the `Authorization: Bearer <sa-token-here>` header instead of as a query parameter for greater security.

Note: The bind host and port settings are only used when transport is set to "http" or "sse".
