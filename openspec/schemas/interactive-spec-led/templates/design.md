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
  One `### Decision: <decision-slug>` block per key technical choice.
  **Binding** is what /opsx:apply treats as non-negotiable — be specific.
  If an explore Decision forced this design choice, name the explore slug
  in **Why**.
-->

### Decision: <decision-slug>

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

<!--
BEFORE FINALIZING — run every check.

Syntactic (grep / wc):
- [ ] No code fences (```) in any Decision block (shell snippets belong
      in tasks.md `verify:` clauses, not here)
- [ ] No `^from .* import` lines (exact import statements belong in tasks
      or implementation, not design)
- [ ] `wc -w < design.md` ≤ 600
- [ ] Every `### Decision: <slug>` block has all four lines: Choice, Why,
      Alternatives, Binding
- [ ] Every `explore/<slug>` referenced in a Why line exists as a
      `### Decision: <slug>` in `explore.md`

Re-classification (re-read each Decision and ask):
- [ ] For each Decision Choice line: "is this an architecture-level
      choice, or a line-level implementation detail?" If the latter
      (enumerated placeholder vocabulary, exact code, specific class
      names beyond the one chokepoint), generalize the prose — the
      specifics belong in tasks.md.
- [ ] For each Binding line: "is this a constraint future code must
      honor, or just a restatement of the Choice?" If the latter,
      sharpen to a testable constraint or delete the line.
-->
