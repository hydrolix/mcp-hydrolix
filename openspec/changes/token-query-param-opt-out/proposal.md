*Let operators turn off the `?token=` query parameter where every client can send the Authorization header.*

**Tracking:** HDX-12410

## Why

The `?token=` query parameter exists because the MCP specification has no static-credential mechanism and not every client can add headers; it stays on by default for them, and the access-log filter redacts the value. A deployment behind a gateway that authenticates callers itself has no header-less clients, and a token in a URL is one more place a credential can be written down. Today there is no way to turn the parameter off.

## What Changes

- New `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM` (default `true`). Only an explicit `false` removes `GetParamAuthBackend` from the authentication chain; the server logs the choice at startup.
- `HydrolixCredentialChain.backends()` becomes the single source of the backend list.
- No behaviour changes by default.

## Capabilities

### New

- `request-credentials` — how a request presents its credential and which forms a deployment accepts.

### Modified

*none*

## Impact

- `mcp_hydrolix/mcp_env.py` — property, docstring line, startup log.
- `mcp_hydrolix/auth/mcp_providers.py` — constructor flag, `backends()`.
- `mcp_hydrolix/mcp_server.py` — passes the flag.
- `README.md`, `docs/CONFIG.md` — "Per-request credentials".
