*Resolved 2 decisions; 2 assumptions; 3 items deferred.*

**Tracking:** HDX-11481

## Questions Asked

- What format should the extended `hdx_query_admin_comment` value use (key=value vs JSON vs `User:` prefix vs slash-separated tag)?
- How should the server behave if `importlib.metadata.version("mcp-hydrolix")` fails at startup (e.g. uninstalled source checkout)?

## Decisions

### Decision: comment-format

- **Question:** What format should the extended `hdx_query_admin_comment` value use?
- **Answer:** Key=value pairs separated by `; `, in the order `User=<name>; version=<version>; transport=<transport>`. Example: `User=mcp-hydrolix; version=0.3.2; transport=stdio`. The existing `User: ` (colon-space) literal is replaced by `User=` — no backwards-compatibility guarantee for grepping the old prefix.
- **Rationale:** Human-readable in Hydrolix query logs, trivially parseable by downstream tools, and avoids JSON noise. Operator explicitly declined the back-compat (`User:` prefix) option.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Query Comment Composition`

### Decision: version-fallback

- **Question:** What should the server do if `importlib.metadata.version("mcp-hydrolix")` raises (e.g. `PackageNotFoundError`)?
- **Answer:** Substitute the literal string `unknown` for the version, log a warning at startup, and continue serving queries. The `version=` field is always emitted; downstream operators can grep `version=unknown` to spot misconfigured deployments.
- **Rationale:** Comment is observability, not a correctness invariant — never block queries on it. Fixed field set keeps parsers simple (no missing-field branch).
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Version Resolution`

## Deferred / Out of Scope

- Including the authenticated principal / per-request user identity in the comment — outside this change's scope; the proposal limits to server-side identity.
- Including bind host/port for `http`/`sse` transports — proposal limits the transport field to the transport name only.
- Making the comment template operator-configurable — no operator demand; defer until a concrete use case appears.

## Assumptions

- `HydrolixConfig.mcp_server_transport` is always resolvable at query time (defaults to `stdio` per `mcp_env.py:217`) — if false, the `transport=` field would be empty or raise, breaking every query's comment line.
- The distribution name passed to `importlib.metadata.version` matches `pyproject.toml` `name = "mcp-hydrolix"` — if renamed without updating the lookup, every install would log the warning and emit `version=unknown`.
