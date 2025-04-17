# Hydrolix MCP Server
[![PyPI - Version](https://img.shields.io/pypi/v/mcp-hydrolix)](https://pypi.org/project/mcp-hydrolix)

An MCP server for Hydrolix.

## Features

### Tools

* `run_select_query`
  - Execute SQL queries on your Hydrolix cluster.
  - Input: `sql` (string): The SQL query to execute.
  - All Hydrolix queries are run with `readonly = 1` to ensure they are safe.

* `list_databases`
  - List all databases on your Hydrolix cluster.

* `list_tables`
  - List all tables in a database.
  - Input: `database` (string): The name of the database.

## Configuration

1. Open the Claude Desktop configuration file located at:
   - On macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

2. Add the following:

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
        "HYDROLIX_PORT": "<hydrolix-port>",
        "HYDROLIX_USER": "<hydrolix-user>",
        "HYDROLIX_PASSWORD": "<hydrolix-password>",
        "HYDROLIX_SECURE": "true",
        "HYDROLIX_VERIFY": "true",
        "HYDROLIX_CONNECT_TIMEOUT": "30",
        "HYDROLIX_SEND_RECEIVE_TIMEOUT": "30"
      }
    }
  }
}
```

Update the environment variables to point to your own Hydrolix service.

3. Locate the command entry for `uv` and replace it with the absolute path to the `uv` executable. This ensures that the correct version of `uv` is used when starting the server. On a mac, you can find this path using `which uv`.

4. Restart Claude Desktop to apply the changes.

### Environment Variables

The following environment variables are used to configure the Hydrolix connection:

#### Required Variables
* `HYDROLIX_HOST`: The hostname of your Hydrolix server
* `HYDROLIX_USER`: The username for authentication
* `HYDROLIX_PASSWORD`: The password for authentication

#### Optional Variables
* `HYDROLIX_PORT`: The port number of your Hydrolix server
  - Default: `8088`
  - Usually doesn't need to be set unless using a non-standard port
* `HYDROLIX_VERIFY`: Enable/disable SSL certificate verification
  - Default: `"true"`
  - Set to `"false"` to disable certificate verification (not recommended for production)
* `HYDROLIX_CONNECT_TIMEOUT`: Connection timeout in seconds
  - Default: `"30"`
  - Increase this value if you experience connection timeouts
* `HYDROLIX_SEND_RECEIVE_TIMEOUT`: Send/receive timeout in seconds
  - Default: `"300"`
  - Increase this value for long-running queries
* `HYDROLIX_DATABASE`: Default database to use
  - Default: None (uses server default)
  - Set this to automatically connect to a specific database
