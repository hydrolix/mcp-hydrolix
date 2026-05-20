<!--
  design.md — HOW to implement. The file is required; sections are optional.
  Omit any section with nothing to say. Don't restate proposal or specs.
  Target: ≤ 2 pages (≈ 600 words).

  For trivial changes with no design-level decisions, replace
  Decisions/Risks/Migration with a single `## Trivial Change` section
  (MUST be operator-confirmed during explore).
-->

*<one-line summary, ≤ 25 words: the design's through-line>*

## Context

<!-- ≤ 8 bullets. Current state + constraints the design must honor. No background recap. -->

- <context>

## Goals / Non-Goals

**Goals:** (≤ 5 bullets)

- <goal>

**Non-Goals:** (≤ 5 bullets)

- <explicitly out of scope>

## Decisions

<!--
  One `### <decision-slug>` block per key technical choice. **Binding** is
  what /opsx:apply treats as non-negotiable — be specific. If an explore
  Decision forced this design choice, name the explore slug in **Why**.
-->

### <decision-slug>

- **Choice:** <what was decided, one sentence>
- **Why:** <rationale, ≤ 3 lines; reference explore/<slug> if applicable>
- **Alternatives:** <each rejected option on one line + reason rejected>
- **Binding:** <the constraint this places on implementation code, e.g. "All callers MUST go through `Foo.create()`">

## Risks / Trade-offs

<!-- `[Risk] → Mitigation`, one per line. -->

- [<risk>] → <mitigation>

## Migration Plan

<!-- Deploy + rollback steps, bullets. Omit if N/A. -->

- <step>

## Open Questions

<!-- Items still unresolved. NOT questions answered by explore.md. -->

- <question>

<!--
## Trivial Change

<one paragraph justifying why this change needs no design-level decisions —
mechanical rename, doc-only, dependency bump with no API surface change.
MUST be operator-confirmed during explore (cite the explore Decision or
No Ambiguity block).
-->
