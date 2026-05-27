*2 decisions; 1 assumption; 2 items deferred.*

**Tracking:** HDX-11481

## Questions Asked

- Format for the extended comment value?
- Behavior when `importlib.metadata.version` fails?

## Decisions

### Decision: comment-format

- **Question:** Format for the extended comment value?
- **Answer:** `User: <name> version: <version> transport: <transport>` (space-separated `key: value` tokens; each key followed by a colon and a single space before the value). Extends the legacy `User: <name>` prefix with two additional tokens.
- **Rationale:** Human-readable, trivially parseable in query logs, and preserves the exact legacy `User: mcp-hydrolix` prefix so existing log scanners keep matching.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Query Comment Composition`

### Decision: version-fallback

- **Question:** Behavior when `importlib.metadata.version("mcp-hydrolix")` fails?
- **Answer:** Emit `version=unknown`, log a warning, continue serving queries.
- **Rationale:** Comment is observability, not a correctness invariant; never block on it.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Version Resolution`

## Deferred / Out of Scope

- Authenticated principal in the comment — out of scope.
- Bind host/port for `http`/`sse` — proposal limits transport to the name only.

## Assumptions

- `HydrolixConfig.mcp_server_transport` is always resolvable at query time (defaults to `stdio`).
