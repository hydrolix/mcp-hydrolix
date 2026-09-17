*Every registered tool is read-only unless it is declared a write tool that requires confirmation, and a test enforces it.*

**Tracking:** HDX-12410

## Why

The server's tools are all read-only today, and clients rely on the `readOnlyHint` annotation to skip confirmation prompts. Nothing stops a future tool from being registered as a write without saying so. A gateway in front of the server (MCPKA) authorizes per tool, so an unmarked write tool would also be invisible to that decision.

## What Changes

- An allow-list in `tests/test_write_tool_policy.py`, empty today, names every tool permitted to write.
- A test asserts that every registered tool not in the list declares `readOnlyHint=True` and `destructiveHint=False`, and that every name in the list is a registered tool declaring `destructiveHint=True`. No source file changes.

## Capabilities

### New

- `write-tool-policy` — the read-only invariant over registered tools and how a write tool is declared.

### Modified

*none*

## Impact

- `tests/test_write_tool_policy.py` — the allow-list and two tests.
- `docs/CONFIG.md` — "Tool policy".
- No source or runtime changes.
