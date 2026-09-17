*A test is the only place the rule bites at build time.*

**Tracking:** HDX-12410

## Context

- All four tools carry `ToolAnnotations(readOnlyHint=True, destructiveHint=False)`.
- MCP clients use `destructiveHint` to decide whether to ask the user before a call; a gateway in front of the server can gate tools individually.

## Goals / Non-Goals

- Goals: make "read-only unless declared" a checked invariant rather than a convention.
- Non-Goals: adding any write tool; changing the gateway's authorization.

## Decisions

### Decision: write-tool-policy-test

- **Choice:** An allow-list of write tools kept in the test module, empty today, plus a test over `mcp.list_tools()`.
- **Why:** Documentation alone enforces nothing; a test fails the suite the moment a tool is registered without the right annotations or without being listed. The allow-list is the test's golden value, so it lives with the test rather than as a constant in the source (review feedback on the first cut).
- **Alternatives:** A runtime check at registration — the failure would surface at startup instead of in CI, with no gain. A constant in `mcp_server.py` — a test expectation in production code, read by nothing at runtime.
- **Binding:** A new write tool MUST be added to the test module's allow-list and MUST declare `destructiveHint=True`, or the suite fails.

## Risks / Trade-offs

- [A contributor adds a write tool to the set without a confirmation flow] → the set's comment states the requirement; the gateway's per-tool authorization is the second line.
