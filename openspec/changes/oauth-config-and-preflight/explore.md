*This change was formed before openspec introduced `explore.md` as a required artifact. No genuine pre-spec audit trail exists; the substantive design choices are recorded in `design.md`. The Q&A below disambiguates one point that an independent reviewer might otherwise misread.*

## Decisions

### Decision: primitive-owns-the-warning

- **Question**: Why does the startup preflight primitive itself emit the WARNING and return `None` on failure, rather than raising and letting the calling activation function decide what to log?
- **Answer**: The fail-open contract — "the worker SHALL emit a single WARNING log line and continue serving with the credential chain only" — is the body of the **Startup Preflight Is Fail-Open** requirement, owned by this change. Co-locating the emitter with the requirement keeps the contract complete in one file. The alternative (caller catches preflight exceptions and logs the WARNING itself) was considered and rejected because it splits ownership of a single WARNING across two changes; an implementer reading either spec alone would be unable to tell what the other emits.
- **Rationale**: The WARNING is a behavioral contract, not an implementation detail. Whoever owns the requirement owns the emission.
- **Affects**: `try_activate_oauth()` signature in `mcp_hydrolix/auth/oauth.py` (returns `OAuthHydrolixAuthProvider | None` instead of raising); design.md "Fail-open contract" line in the Goals section; tasks.md task 3.1.
