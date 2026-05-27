*Resolved 0 decisions; 2 assumptions; 2 items deferred.*

## Questions Asked

*none — see No Ambiguity below*

## No Ambiguity

The parent decomposition task (the fan-out orchestrator prompt on 2026-05-27) provided complete, authoritative answers for every dimension of this sub-spec: the exact requirements to include (R03, R13, and the request-time half of R04), the positive framing for R03, the three design decisions to carry forward (activation site, `asyncio.run` inside the factory, `mcp.auth` assignment seam), the two decisions to drop (`_maybe_activate_oauth` rename and gunicorn dead-code), the composition order (OAuth verifier first, SA chain second), and the implementation surface (`mcp_providers.py`, `webapp.py`). No operator clarification was needed beyond that specification. Operator confirmed via the orchestrator prompt.

## Deferred / Out of Scope

- Prometheus counter for OAuth activation failures per worker — useful for operability; deferred to a follow-up unless on-call surfaces a need.
- Multi-worker integration test on staging cluster — covered by the staging gate in the parent change; unit-level smoke test suffices here.

## Assumptions

- `OAuthBearerToken` and `OAuthHydrolixAuthProvider` are provided by the `oauth-jwt-verifier` sub-spec and are available as imports before this sub-spec's code runs — if that sub-spec is absent, `ChainedAuthBackend` cannot be assembled.
- FastMCP's `mcp.auth` attribute is a publicly supported post-construction seam (the same value the `FastMCP(auth=...)` constructor would store) — if FastMCP changes the internal field name or removes the attribute, the activation assignment will fail silently or raise `AttributeError`.
