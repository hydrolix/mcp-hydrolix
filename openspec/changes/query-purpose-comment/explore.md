*Resolved 1 decision.*

**Tracking:** HDX-12008

## Questions Asked

- Should the purpose comment ship together with the wider query-attribution change?

## Decisions

### Decision: standalone-change

- **Question:** Should the purpose comment ship together with the wider query-attribution change?
- **Answer:** No. The repository maintainer asked for it as its own change in the 2026-09-16 review because it is independently reviewable and uses `hdx_query_comment` for exactly what the field is for.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Query Purpose Comment`

## Verification

- 2026-09-16, qe-innovations-3 (Hydrolix v6.4.0-rc.1): a query sent with `hdx_query_comment` as a transport-level setting landed in `hydro.logs.hdx_query_comment` unchanged.
