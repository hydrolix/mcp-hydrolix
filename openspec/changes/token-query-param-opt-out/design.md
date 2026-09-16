*Default on, opt out per deployment.*

**Tracking:** HDX-12410

## Context

- `HydrolixCredentialChain.get_middleware` builds a fixed chain: `BearerAuthBackend` then `GetParamAuthBackend`.
- `AccessLogTokenRedactingFilter` already redacts `token=` values from access logs.
- At least one external deployment runs the server as a remote HTTP service outside a cluster and must keep working on upgrade; the README documents the query-parameter form.

## Goals / Non-Goals

- Goals: a per-deployment switch; identical behaviour when the variable is unset.
- Non-Goals: removing the query-parameter form; changing how a token is verified.

## Decisions

### Decision: default-on-opt-out

- **Choice:** `HYDROLIX_ALLOW_TOKEN_QUERY_PARAM` defaults to `true`; only an explicit `false` disables the backend.
- **Why:** The maintainer described the parameter as a necessary evil for clients that cannot send headers and asked for an opt-out rather than an opt-in (2026-09-16 review), so no existing deployment changes on upgrade. Matching `HYDROLIX_QUERY_TIMERANGE_REQUIRED`, a typo keeps the permissive default rather than silently locking clients out.
- **Alternatives:** Off by default — breaks header-less clients and the documented remote deployment on upgrade. Remove the backend — no path for those clients at all.
- **Binding:** `HydrolixCredentialChain.backends()` MUST be the single source of the backend list, `BearerAuthBackend` MUST come first, and the server MUST log at startup when the parameter is disabled.

## Risks / Trade-offs

- [Operator disables it while a header-less client is in use] → that client gets 401 on every request; the startup log names the variable.
