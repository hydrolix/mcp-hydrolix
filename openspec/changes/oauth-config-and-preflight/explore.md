*Resolved 0 decisions; 3 assumptions; 2 items deferred.*

## Questions Asked

*none — see No Ambiguity below*

## No Ambiguity

The content and decisions for this sub-spec were extracted from a fully-resolved parent change (`oauth-prototype-productionize`) by a fan-out decomposition task. The operator's instruction message on 2026-05-27 identified exactly which requirements, scenarios, and design decisions belong to this sub-spec (R01, R02, R10, and the startup half of R04), specified how to split R04 and retitle it, specified which design decisions to carry in, and named the reader persona constraints. No behavioral ambiguity remained: the activation precedence chain, the two-exception taxonomy, the single-IdP-coupling-point shape, and the insecure-JWKS guard are all resolved in the source material. No questions were needed.

## Deferred / Out of Scope

- Full `canonical_idp_endpoints()` implementation — deferred pending [HDX-11431](https://hydrolix.atlassian.net/browse/HDX-11431); the stub and its contract tests are in scope; the body is a future one-function diff.
- Prometheus counter for OAuth activation failures — deferred to a follow-up as noted in the source design's Open Questions.

## Assumptions

- The `OAuthConfig` dataclass and `load_oauth_config()` already exist in the prototype (`il/feature/oauth-support/hdx-11133`) and will be ported to `mcp_hydrolix/auth/oauth.py`; this sub-spec specifies their behavioral contract, not a greenfield implementation — if the prototype surface changes materially, the spec may need revision.
- `HYDROLIX_URL` is provided by [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441); this sub-spec consumes it as a string read from the environment and does not validate its format beyond what `canonical_idp_endpoints()` requires — if [HDX-11441](https://hydrolix.atlassian.net/browse/HDX-11441)'s URL-validation rules change, the derivation path here inherits those changes without a spec update.
- The `create_app()` factory in `webapp.py` runs in a fresh worker process before uvicorn's event loop starts, making a top-level `asyncio.run()` call safe; if the factory is ever moved under a running loop, the activation code must be refactored and this assumption becomes false.
