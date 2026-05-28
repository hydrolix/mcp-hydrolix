*Audit every `logger.*` call site in the MCP auth layer to guarantee no JWT credential material ever appears in log output.*

## Why

Log aggregation pipelines in Kubernetes clusters are not secret stores. Any raw JWT, bearer string, or JWKS private exponent that reaches a log line is permanently exposed to anyone with log-read access — a replay or forgery risk that cannot be patched after the fact. This audit closes that gap before OAuth reaches production.

## Family Context / Forward References

One of 5 changes decomposing OAuth bearer authentication for [HDX-11442](https://hydrolix.atlassian.net/browse/HDX-11442). All five target the shared capability `oauth-authentication`. This change is **orthogonal** — it does not depend on the other four, and they do not depend on it.

- `oauth-config-and-preflight` — env-var activation gate, canonical IdP derivation, JWKS preflight.
- `oauth-resource-metadata` — RFC 9728 protected-resource-metadata endpoint.
- `oauth-jwt-verifier` — JWT claim validation with iss-based routing.
- `oauth-auth-chain-and-activation` — flat auth chain composition and per-worker activation.
- `oauth-log-redaction` (this change) — log-redaction invariant across the auth layer.

## What Changes

- Extend the `oauth-authentication` capability with log-redaction requirements specifying what the auth layer MAY and SHALL NOT log for three call paths: successful activation, valid bearer accepted, and invalid bearer rejected.
- The log-redaction guarantee is a CI-enforced invariant covering 6 call paths, not a code-review convention.
- Auth-layer error paths that could expose raw token bytes emit only the exception class name.

## Capabilities

### New

*none*

### Modified

- `oauth-authentication` — adds the log-redaction invariant: no JWT credential material may appear in any auth-layer log record

## Impact

- `mcp_hydrolix/auth/oauth.py` — audit `logger.*` calls; replace any that could emit raw JWT bytes.
- `mcp_hydrolix/auth/mcp_providers.py` — audit `logger.*` calls in the provider composition layer.
- `mcp_hydrolix/mcp_server.py` — audit any auth-adjacent log calls.
- `mcp_hydrolix/webapp.py` — audit activation-path log calls in `_activate_oauth_if_configured`.
- `tests/auth/test_log_redaction.py` — new test module; `caplog` assertions across 6 call paths.
- No new dependencies; no behavior change beyond log-line shape.
- Orthogonal to all other oauth changes: this is a cross-cutting audit on `logger.*` call sites with no dependency on config gating, JWT verification logic, resource metadata, or auth-chain composition order.
