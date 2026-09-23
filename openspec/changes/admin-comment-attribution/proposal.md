*Name the token subject and the agent in `hdx_query_admin_comment`, keeping the connector-wide `User: … version: … transport: …` prefix.*

**Tracking:** HDX-12008

## Why

Every query from a deployment writes the same `hdx_query_admin_comment`, so `hydro.logs` cannot say who ran a query or through which agent. The field is the first-party application-identification field and already lands in `hydro.logs` and `hdx.active_queries`; the same `User: <app>` prefix is written by the other Hydrolix connectors and parsed by the usage analytics, so it must stay exactly as it is.

## What Changes

- `hdx_query_admin_comment` is built per request: the existing static prefix, then optional colon-separated `sub`, `agent`, `model`, `session` and `trace` tokens.
- New module `mcp_hydrolix/attribution.py` owns the vocabulary, sanitisation, the 512-byte budget and the source precedence (gateway headers, then MCP `_meta`, then `initialize` client info).
- Attribution never raises; a missing field is omitted.

## Capabilities

### New

*none*

### Modified

- `query-admin-comment` — the composition requirement gains the request tokens; a new requirement covers the attribution sources.

## Impact

- `mcp_hydrolix/attribution.py` (new, pure), `mcp_hydrolix/middlewares/request_attribution.py` (new, the middleware), `mcp_hydrolix/auth/credentials.py` (`subject`), `mcp_hydrolix/mcp_server.py` (`_APP_IDENTITY`, the middleware registration, three lines in `execute_query`).
- `docs/CONFIG.md` "Query attribution".
- `HDX_ADMIN_COMMENT` keeps its exact legacy value, so existing tests and analytics are unaffected.
