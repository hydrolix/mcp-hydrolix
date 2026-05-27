*Log-line shape is a tested contract: `caplog` assertions across 6 call paths enforce it on every PR.*

## Context

- The MCP auth layer spans four files: `mcp_hydrolix/auth/oauth.py`, `mcp_hydrolix/auth/mcp_providers.py`, `mcp_hydrolix/mcp_server.py`, `mcp_hydrolix/webapp.py`.
- JWT bearer tokens travel as `Authorization: Bearer <header>.<payload>.<signature>` strings; any of the three segments is sufficient to reassemble a usable token if logged.
- Exception handlers in JWT-parsing libraries frequently include the raw input in the exception message. A naive `logger.exception(exc)` or `logger.error(str(exc))` call is therefore a redaction failure point.
- `caplog` in pytest captures Python `logging.LogRecord` objects, giving access to both `record.getMessage()` (the formatted string) and `record.args` (the unformatted arguments), which together cover every path a value can take before it reaches a log sink.
- This sub-spec is orthogonal to the other four oauth sub-specs. It has no upstream or downstream dependency on config gating, JWT verification logic, RFC 9728 resource metadata, or auth-chain composition order. It is a cross-cutting audit on `logger.*` call sites in the auth layer that can be reviewed and merged independently.

## Goals / Non-Goals

**Goals:**
- Every `logger.*` call in the auth layer is audited and, where necessary, modified so no prohibited content reaches a log record.
- The redaction guarantee is a CI-enforced invariant, not a one-time audit.
- Tests are black-box with respect to log-line wording; they assert on prohibited content categories, not exact strings.

**Non-Goals:**
- Changing log verbosity or adding new log lines (this change is content-shape only).
- Auditing log calls outside the auth layer (non-auth modules are out of scope).
- Structured logging or log-sink configuration (out of scope for this change).

## Decisions

### Decision: log-content-is-tested-invariant

- **Choice:** Log content for the auth layer is a tested invariant backed by `caplog` assertions, not a code-review convention.
- **Why:** A code-review convention can be bypassed by any future `logger.exception(exc)` or debug log added without a corresponding redaction review. A `caplog`-based test that runs on every PR fails loudly if any new log call introduces prohibited content, making the constraint self-enforcing. This rationale is carried directly from the parent change (`oauth-prototype-productionize` design.md: "Log content is a tested invariant").
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
- **Why:** Python's logging system stores the format string and arguments separately until the record is formatted by a handler. A prohibited value can therefore appear in `record.args` even if `record.getMessage()` does not surface it (e.g. when the format string never interpolates the argument, or when the argument is a complex object whose `__str__` is not called until formatting). Checking both closes this gap.
- **Alternatives:**
  - Check only `record.getMessage()` — misses raw arguments that are not interpolated.
  - Serialize the entire record to a string and scan — equivalent but less targeted.
- **Binding:** The `caplog` test helpers in `tests/auth/test_log_redaction.py` MUST scan both `record.getMessage()` and `record.args` (flattened) for each prohibited content category.

## Risks / Trade-offs

- `[Risk] Tests are brittle if prohibited-content checks use overly broad patterns` → Mitigation: checks are keyed on specific token components (signature segment, base64url pattern of known length) rather than arbitrary substrings; test tokens are minted with distinct values to make false positives obvious.
- `[Risk] A new auth-layer file added outside the four audited files escapes coverage` → Mitigation: document the four file scope explicitly in the spec; a PR adding a fifth auth file without a corresponding test expansion will have no `caplog` coverage for it, which is a code-review signal.

## Open Questions

*none*
