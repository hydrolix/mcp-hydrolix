# Hydrolix MCP Bundle

This bundle lets you query Hydrolix from Claude without editing any config files by hand.

## Installation

### Claude Desktop

Drag and drop the `.mcpb` file into Claude Desktop. Claude Desktop will show a configuration form where you fill in your connection details, then save and launch the server automatically.

### VS Code

Open the Command Palette (`Cmd+Shift+P` on macOS, `Ctrl+Shift+P` on Windows/Linux), run **MCP: Install from Bundle**, and select the `.mcpb` file.

## Configuration

You will be prompted for the following fields:

| Field | Required | Notes |
|---|---|---|
| Hydrolix Host | Yes | Hostname of your cluster, e.g. `mycluster.hydrolix.live` |
| Service Account Token | No | Preferred auth method. Leave blank to use username/password instead. |
| Username | No | Used with Password when no token is set. |
| Password | No | Used with Username when no token is set. |
| Default Database | No | Leave blank to use the cluster default. |

## Available Tools

Once installed, the following tools are available in conversations:

- `run_select_query`: execute a SELECT SQL query on your Hydrolix cluster
- `list_databases`: list all databases on the cluster
- `list_tables`: list all tables in a given database
- `get_table_info`: return schema and metadata for a table

## Requirements

- Python 3.13 or later (resolved automatically by `uv` on first launch)
- `uv` must be installed and on your PATH

## Full Documentation

See the [mcp-hydrolix README](https://github.com/hydrolix/mcp-hydrolix) for complete documentation, including alternative install methods and configuration options.

## Issues

Please file issues at https://github.com/hydrolix/mcp-hydrolix/issues.
