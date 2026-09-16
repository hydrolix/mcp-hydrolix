*The purpose is observability: never a failure path, never parsed by the server.*

**Tracking:** HDX-12008

## Context

- `execute_query` builds the transport-level settings dict for every query; `hdx_query_comment` is a Hydrolix query setting that already reaches `hydro.logs` and `hdx.active_queries`.
- `strip_conflicting_settings` protects every key in that dict from an inline override, so the recorded purpose is the tool argument, not something written into the SQL text.

## Goals / Non-Goals

- Goals: give operators the agent's stated reason for a query, in a field that already exists, with no schema change and no new failure mode.
- Non-Goals: validating or interpreting the purpose; attribution of the principal or agent identity (a separate change).

## Decisions

### Decision: purpose-as-tool-argument

- **Choice:** An optional `purpose` string on `run_select_query`, forwarded as `execute_query(comment=)`.
- **Why:** The tool call is where the agent knows why it is querying; anything placed in the SQL text would be stripped or ignored.
- **Alternatives:** Require the argument — breaks every existing client. Derive it from the SQL — guesswork.
- **Binding:** `execute_query` MUST omit `hdx_query_comment` when the sanitized purpose is empty and MUST cap it at 256 characters.

## Risks / Trade-offs

- [Agents pass long or multi-line text] → collapsed to single spaces and capped; nothing fails.
- [Agents omit the purpose] → the setting is absent, exactly as today.
