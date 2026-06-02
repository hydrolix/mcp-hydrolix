*This change was formed before openspec introduced `explore.md` as a required artifact. No genuine pre-spec audit trail exists; the substantive design choices are recorded in `design.md`. The Q&A below disambiguates one point that an independent reviewer might otherwise misread.*

## Decisions

### Decision: unverified-iss-peek-is-routing-only

- **Question**: The OAuth verifier peeks the bearer JWT's `iss` claim **without** verifying the signature, then uses it to decide whether to claim the token or defer to the next backend. How is this not a security gap — couldn't an attacker forge `iss` to manipulate routing?
- **Answer**: The unverified peek is used **only** for routing (which backend in the chain claims the bearer). Full JWKS signature verification still gates every success path. An attacker who sets `iss = <our-OAuth-issuer>` on a forged token: this verifier claims the bearer (`iss` matches) → JWKS signature check fails → 401. An attacker who sets `iss = <SA-issuer>`: this verifier defers → `BearerAuthBackend` (the SA verifier) attempts its own signature check against the SA public key → fails → 401. Either way the request is rejected. The peek influences routing only, not authentication; no codepath grants access based on the unverified claim.
- **Rationale**: Hydrolix service-account bearer tokens are themselves JWTs and share the `Authorization: Bearer` header. Routing has to happen somewhere; doing it via the `iss` claim mirrors the upstream `turbine-api` [`TokenValidator.validate_token`](https://github.com/hydrolix/turbine/blob/0f072549d775ae8d6384fabcb26fe3c224a719f5/turbine-api/common/rest_framework/authentication/token_validator.py#L115-L137)'s own dispatch strategy and aligns the two systems' routing semantics.
- **Affects**: `OAuthHydrolixAuthProvider`'s claim/defer/raise contract; the **OAuth Verifier Claims Bearers By Iss Match** requirement in spec.md.
