*Resolved 1 decision.*

**Tracking:** HDX-12410

## Questions Asked

- Should the `?token=` query parameter be off by default and enabled where needed, or on by default with an opt-out?

## Decisions

### Decision: opt-out-not-opt-in

- **Question:** Off by default with an opt-in, or on by default with an opt-out?
- **Answer:** On by default with an opt-out. In the 2026-09-16 review the repository maintainer described the parameter as the only way within the MCP specification to present a static token to a client that cannot send headers, noted the access-log redaction that already exists for it, and expected the change to be "a flag that allows it by default, but you can opt out". Deployments whose clients can all send the header, such as one behind an authenticating gateway, turn it off.
- **Affects:** `specs/request-credentials/spec.md → Requirement: Token Query Parameter Opt-Out`
