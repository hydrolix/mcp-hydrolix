*This change was formed before openspec introduced `explore.md` as a required artifact. No genuine pre-spec audit trail exists; the substantive design choices are recorded in `design.md`. The Q&A below disambiguates one point that an independent reviewer might otherwise misread.*

## Decisions

### Decision: redaction-is-cross-cutting-not-embedded

- **Question**: Why is log redaction a single cross-cutting change rather than embedded in each of the other changes that emit logs in the auth layer?
- **Answer**: The redaction invariant must hold across **every** `logger.*` call in the auth layer, regardless of which change introduced the call. A single change with a single test module that exercises all six call paths (successful activation, discovery failure, valid bearer accepted, invalid bearer rejected, SA path with no bearer, `OAuthConfigError` raised) keeps the invariant testable as a unit and easy to extend when future auth-layer changes introduce new log emitters. Embedding it would scatter the invariant across four+ test files and risk drift — a `logger.exception(exc)` added in one change could leak a token via the exception message without anyone noticing if the redaction check lived only in the OTHER change's tests.
- **Rationale**: A cross-cutting safety property is easier to maintain as a single audit than as policy embedded in every code site that could violate it.
- **Affects**: The orthogonal position of this change in the dependency graph; tests live in `tests/auth/test_log_redaction.py` and are not duplicated in other auth tests.
