*Resolved 0 decisions; 2 assumptions; 0 items deferred.*

## Questions Asked

*none — see No Ambiguity below*

## No Ambiguity

This change is a fully specified cross-cutting audit. The parent change `oauth-prototype-productionize` already captured the key design decision ("Log content is a tested invariant", `design.md` line) and enumerated the exact 6 call paths, the 5 prohibited content categories, and the 3 spec scenarios verbatim. The proposal adds no UX choices, no migration shape, no breaking-vs-compat trade-offs, and no edge cases left open. Operator confirmation was provided in the agent task instructions (fan-out decomposition brief, 2026-05-27) which specified all requirement text, all scenario names, and the full test surface for this sub-spec.

## Deferred / Out of Scope

*none*

## Assumptions

- The 6 call paths enumerated in the test surface (successful activation, discovery failure, valid bearer accepted, invalid bearer rejected, SA path with no bearer, `OAuthConfigError` raised) are exhaustive for the auth layer's logging surface — if a seventh path is discovered at implementation time, the spec scenarios should be updated.
- Decoded claim values (`sub`, `aud`, `iss`, etc.) are not considered credentials and are safe to log — this assumption holds as long as the IdP signs tokens with private keys that are never derivable from claims alone.
