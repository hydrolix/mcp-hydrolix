# Hydrolix MCP Server
[![PyPI - Version](https://img.shields.io/pypi/v/mcp-hydrolix)](https://pypi.org/project/mcp-hydrolix)

An MCP server for Hydrolix.

## Tools

* `run_select_query`
  - Execute SQL queries on your Hydrolix cluster.
  - Input: `sql` (string): The SQL query to execute.
  - All Hydrolix queries are run with `readonly = 1` to ensure they are safe.

* `list_databases`
  - List all databases on your Hydrolix cluster.

* `list_tables`
  - List all tables in a database.
  - Input: `database` (string): The name of the database.

## Effective Usage

Due to the wide variety in LLM architectures, not all models will proactively use the tools above, and few will use them effectively without guidance, even with the carefully-constructed tool descriptions provided to the model. To get the best results out of your model while using the Hydrolix MCP server, we recommend the following:

* Refer to your Hydrolix database by name and request tool usage in your prompts (e.g., "Using MCP tools to access my Hydrolix database, please ...")
  - This encourages the model to use the MCP tools available and minimizes hallucinations.
* Include time ranges in your prompts (e.g., "Between December 5 2023 and January 18 2024, ...") and specifically request that the output be ordered by timestamp.
  - This prompts the model to write more efficient queries that take advantage of [primary key optimizations](https://hydrolix.io/blog/optimizing-latest-n-row-queries/)

## Configuration

The Hydrolix MCP server is configured using a standard MCP server entry. Consult your client's documentation for specific instructions on where to find or declare MCP servers. An example setup using Claude Desktop is documented below.

The recommended way to launch the Hydrolix MCP server is via the [`uv` project manager](https://github.com/astral-sh/uv), which will manage installing all other dependencies in an isolated environment.

MCP Server definition (JSON):

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

MCP Server definition (YAML):

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

### Configuration Example (Claude Desktop)

1. Open the Claude Desktop configuration file located at:
   - On macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

2. Add a `mcp-hydrolix` server entry to the `mcpServers` config block:

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

3. Update the environment variable definitions to point to your Hydrolix cluster.

4. (Recommended) Locate the command entry for `uv` and replace it with the absolute path to the `uv` executable. This ensures that the correct version of `uv` is used when starting the server. You can find this path using `which uv` or `where.exe uv`.

5. Restart Claude Desktop to apply the changes. If you are using Windows, ensure Claude is stopped completely by closing the client using the system tray icon.

### Environment Variables

The following variables are used to configure the Hydrolix connection. These variables may be provided via the MCP config block (as shown above), a `.env` file, or traditional environment variables.

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
* `HYDROLIX_DATABASE`: Default database to use
  - Default: None (uses server default)
  - Set this to automatically connect to a specific database
