*Resolved 1 decision; 1 verification.*

**Tracking:** HDX-12410

## Questions Asked

- Where should the wire format be imposed so that an agent's FORMAT clause stops failing queries?

## Decisions

### Decision: driver-owns-the-format

- **Question:** Where should the wire format be imposed?
- **Answer:** Nowhere new. The driver already imposes `FORMAT Native`; the server removes the agent's clause so there is only one. The maintainer asked for this fix in the 2026-09-16 review and suggested JSONCompact; that applies to implementations that speak raw HTTP, not to this driver-based one.
- **Affects:** `specs/query-text-handling/spec.md → Requirement: Format Clause Removed`

## Verification

- 2026-09-16, ClickHouse 26 (compose) and Hydrolix v6.4.0-rc.1 (qe-innovations-3): `SELECT 1 AS x FROM system.one FORMAT JSON` through `execute_query` fails with code 62 at the driver-appended `FORMAT Native`; the same text sent alone over HTTP returns 200.
