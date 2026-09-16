*Resolved 2 decisions; 1 verification.*

**Tracking:** HDX-12008

## Questions Asked

- Replace the admin comment's format, or extend it?
- What key names the human or service-account identity?

## Decisions

### Decision: extend-not-replace

- **Question:** Replace the admin comment's format, or extend it?
- **Answer:** Extend. The repository maintainer stated in the 2026-09-16 review that the `User: … version: … transport: …` shape and its colon separators are shared with the other connectors and parsed by the existing usage analytics, and asked that they stay; new fields may be appended.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Query Comment Composition`

### Decision: sub-key

- **Question:** What key names the identity?
- **Answer:** `sub`, the token's subject claim: the key the gateway's identity model, its audit log and the cluster's external identities all use, and the one that stays unambiguous if RFC 8693 delegation adds an actor later.
- **Affects:** `specs/query-admin-comment/spec.md → Requirement: Query Comment Composition`

## Verification

- 2026-09-16, qe-innovations-3 (Hydrolix v6.4.0-rc.1): a comment in the extended shape sent as a transport-level setting landed in `hydro.logs.hdx_query_admin_comment` byte-for-byte within about three minutes; the column's existing top values there are `User: kibana-gateway` and `Anomaly Detection Job: <uuid>`.
