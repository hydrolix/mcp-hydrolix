*Resolved 1 decision; 2 verifications.*

**Tracking:** HDX-12410

## Questions Asked

- Should the default caps be argued in advance or adjusted on feedback?

## Decisions

### Decision: reactive-defaults

- **Question:** Should the default caps be argued in advance or adjusted on feedback?
- **Answer:** On feedback. The repository maintainer said in the 2026-09-16 review that every change to these limits draws complaints and that he prefers fixing the number afterwards to predicting it; this change picks 200000 cells and 64 MiB and names the variables in the release notes.
- **Affects:** `specs/result-limits/spec.md → Requirement: Caller Lowerable Cell Cap`

## Verification

- 2026-09-16, qe-innovations-3 (Hydrolix v6.4.0-rc.1): `hdx_query_max_result_bytes=10000` as a transport-level setting cancelled an 818 KiB result with code 396; an unknown `hdx_query_*` setting was ignored; an inline `SETTINGS hdx_query_max_result_rows` outranked the transport-level value.
