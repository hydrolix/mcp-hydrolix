*Resolved 0 decisions; 3 assumptions; 2 items deferred.*

## Questions Asked

*none — see No Ambiguity below*

## No Ambiguity

The capability scope, requirement text, scenario set, and all key design decisions are fully specified in the decomposition instructions provided in the originating agent prompt (2026-05-27). The source material (`openspec/changes/oauth-prototype-productionize/specs/oauth-authentication/spec.md` requirements R05, R06, R07, R12 and `design.md` decision "Non-conflation is a verifier invariant, not a startup check") leaves no behavioral gaps that require operator clarification before writing specs. Operator confirmed via the task-assignment prompt that this sub-spec should be written autonomously from the provided source material.

## Deferred / Out of Scope

- Refresh-token flow, token introspection, DPoP — out of scope per design.md Non-Goals; JWKS-local verification only.
- Prometheus counter for per-request verification outcomes — deferred to a follow-up; not required by R05–R07, R12.

## Assumptions

- `OAuthConfig.issuer`, `OAuthConfig.audience`, and `OAuthConfig.required_scopes` are parsed and validated upstream by `oauth-config-and-preflight`; this verifier receives them as already-valid values — if upstream parsing changes its field names, verifier code must be updated.
- FastMCP's `JWTVerifier` supports pluggable issuer, audience, and scope constraints sufficient to implement R05, R06, R07 — if it does not, a thin wrapper or custom claim-check layer replaces the direct delegation.
- Tests use mocked JWTs (no live IdP required) and a mock JWKS provider — if the test framework cannot generate RS256-signed JWTs in-process, a fixture library (e.g. `python-jose`) must be added as a test dependency.
