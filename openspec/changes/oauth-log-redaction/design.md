*Log-line shape is a tested contract: `caplog` assertions across 6 call paths enforce it on every PR.*

## Context

- The MCP auth layer spans four files: `mcp_hydrolix/auth/oauth.py`, `mcp_hydrolix/auth/mcp_providers.py`, `mcp_hydrolix/mcp_server.py`, `mcp_hydrolix/webapp.py`.
- Any single JWT segment (`header`, `payload`, or `signature`) is sufficient to reassemble a usable token if logged.
- JWT-parsing libraries frequently include the raw input in exception messages; a naive `logger.exception(exc)` is therefore a redaction failure point.
- `caplog` captures both `record.getMessage()` and `record.args`, covering every path a value can take before reaching a log sink.
- This sub-spec is orthogonal to all other oauth sub-specs; it can be reviewed and merged independently.

## Goals / Non-Goals

**Goals:** Every `logger.*` call in the auth layer is audited and hardened so no prohibited content reaches a log record; the guarantee is CI-enforced, not a code-review convention.

**Non-Goals:** Changing log verbosity; auditing non-auth modules; structured logging or log-sink configuration.

## Decisions

### Decision: log-content-is-tested-invariant

- **Choice:** Log content for the auth layer is a tested invariant backed by `caplog` assertions, not a code-review convention.
- **Why:** A code-review convention degrades under time pressure; a `caplog` test that runs on every PR fails loudly if any new log call introduces prohibited content, making the constraint self-enforcing.
- **Alternatives:**
  - Lint rule / AST check — detects static patterns only; misses dynamic cases where a token value flows into a log call via an intermediate variable.
  - Code-review checklist — no CI enforcement; degrades under time pressure.
- **Binding:** All `logger.*` calls added or modified in the auth layer MUST be covered by the `caplog` test suite in `tests/auth/test_log_redaction.py`. Any new `logger.exception(exc)` call in the auth layer MUST log only `type(exc).__name__`, not `str(exc)`, when the exception could quote raw token bytes.

### Decision: exception-class-name-only

- **Choice:** When an exception message could contain raw token bytes, the auth layer logs `type(exc).__name__` only.
- **Why:** JWT parser libraries (e.g. `python-jose`, `PyJWT`) include the malformed input in their exception messages on parse errors. Logging the full exception message would therefore be a redaction failure for invalid-token paths. Logging just the class name preserves enough diagnostic information (the failure category) without exposing credential material.
- **Alternatives:**
  - Sanitize the exception message with a regex — fragile and hard to maintain as library error-message formats change.
  - Suppress logging on error paths — removes operational visibility.
- **Binding:** On the invalid-bearer-rejected and discovery-failure call paths, the auth layer MUST log `type(exc).__name__` (or an equivalent that does not include `str(exc)`) rather than the full exception representation.

### Decision: caplog-checks-args-and-message

- **Choice:** `caplog` assertions check both `record.getMessage()` and each element of `record.args`, not only the final formatted string.
- **Why:** Python logging stores the format string and arguments separately; a prohibited value can appear in `record.args` even if `record.getMessage()` does not surface it. Checking both closes this gap.
- **Alternatives:**
  - Check only `record.getMessage()` — misses raw arguments that are not interpolated.
  - Serialize the entire record to a string and scan — equivalent but less targeted.
- **Binding:** The `caplog` test helpers in `tests/auth/test_log_redaction.py` MUST scan both `record.getMessage()` and `record.args` (flattened) for each prohibited content category.

## Risks / Trade-offs

- `[Risk] Tests are brittle with overly broad patterns` → Mitigation: checks key on specific token components (signature segment, base64url pattern of known length); test tokens are minted with distinct values to surface false positives.
- `[Risk] A new auth-layer file escapes coverage` → Mitigation: the four-file scope is explicit in the spec; a fifth file without a corresponding test expansion has no `caplog` coverage — a visible code-review signal.

## Open Questions

*none*
