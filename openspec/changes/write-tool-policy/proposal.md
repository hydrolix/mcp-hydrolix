*Every registered tool is read-only unless it is declared a write tool that requires confirmation, and a test enforces it.*

**Tracking:** HDX-12410

## Why

The server's tools are all read-only today, and clients rely on the `readOnlyHint` annotation to skip confirmation prompts. Nothing stops a future tool from being registered as a write without saying so. A gateway in front of the server (MCPKA) authorizes per tool, so an unmarked write tool would also be invisible to that decision.

## What Changes

- `WRITE_TOOLS_REQUIRING_CONFIRMATION`, an empty set in `mcp_hydrolix/mcp_server.py`, names every tool allowed to write.
- A test asserts that every registered tool not in the set declares `readOnlyHint=True` and `destructiveHint=False`, and that every name in the set is a registered tool declaring `destructiveHint=True`.

## Capabilities

### New

- `write-tool-policy` — the read-only invariant over registered tools and how a write tool is declared.

### Modified

*none*

## Impact

- `mcp_hydrolix/mcp_server.py` — one constant and its comment.
- `tests/test_write_tool_policy.py` — two tests.
- `docs/CONFIG.md` — "Tool policy".
- No runtime behaviour changes.
