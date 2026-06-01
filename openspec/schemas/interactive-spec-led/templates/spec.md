<!--
  spec.md — WHAT the system shall do, in requirement-style (RFC 2119 /
  BCP 14: MUST, SHALL, SHOULD, MAY), testable form.

  Headers (silent-failure traps; the formatter is strict):
  - `## ADDED | MODIFIED | REMOVED Requirements`
  - `### Requirement: <Title Case Name>`  ← words separated by spaces, e.g.
    "Activation Gated On Env Vars". Tasks cite the kebab-case slug derived
    from this heading (lowercase, spaces → `-`, strip non-alphanumeric).
  - `#### Scenario: <Title Case Scenario Name>` — EXACTLY 4 hashtags;
    3 hashtags or a bullet parses as part of the requirement description
    and the scenario is lost.

  Scenario bullets (Gherkin-style):
  - `- **GIVEN** <precondition>` — RECOMMENDED when there's prior state.
  - `- **WHEN** <trigger>` — the firing event.
  - `- **THEN** <outcome>` — the assertion.
  - `- **AND** <additional>` — continues whichever block it follows.

  HARD RULE for MODIFIED and REMOVED requirements:
    Header line MUST be byte-identical (whitespace-insensitive) to the
    existing header in openspec/specs/<cap>/spec.md. Mismatch fails the
    operation at archive time — MODIFIED silently loses your edits;
    REMOVED silently leaves the requirement in place — no error is
    surfaced. Diff after pasting.

  Style: use RFC 2119 / BCP 14 keywords (MUST, SHALL, SHOULD, MAY and
  negatives) with their RFC 2119 meanings. PREFER MUST / SHALL for binding
  requirements; SHOULD / MAY are valid for recommendations and permissions.
  Every requirement has ≥ 1 scenario.

  This template shows all three delta sections. Delete the sections that
  don't apply to this change rather than commenting them out.

  Tracing explore Decisions: add `<!-- settle: explore/<slug> -->` on its
  own line immediately AFTER the requirement statement (and after a
  scenario's bullets) that implements an explore decision — never directly
  under the heading, where a leading comment masks the requirement's RFC
  2119 keyword and fails `openspec validate`.

  Anti-patterns:
  - Lowercase `should` / `may` (use uppercase RFC 2119 keywords; only the
    uppercase forms carry their RFC 2119 meaning).
  - Scenario with WHEN but no THEN (or vice versa).
  - Requirement with zero scenarios.
  - Title-Case-With-Spaces-Wrong-Form (e.g. `kebab-case` or `PascalCase`
    requirement headings; OpenSpec archive expects Title Case With Spaces).
  - MODIFIED or REMOVED block header that doesn't byte-match the existing spec.
-->

*<one-line summary, ≤ 25 words: what this capability covers>*

## ADDED Requirements

### Requirement: <Title Case Name>

<one-sentence requirement statement using RFC 2119 / BCP 14 keywords (prefer MUST / SHALL)>

<!-- settle: explore/<slug> -->

#### Scenario: <Short Scenario Name>

- **GIVEN** <precondition state, optional>
- **WHEN** <trigger event>
- **THEN** <observable outcome>
- **AND** <additional outcome, optional>

## MODIFIED Requirements

<!--
  Copy the ENTIRE existing requirement block (header + every scenario) from
  openspec/specs/<cap>/spec.md, then edit. Header MUST be byte-identical
  (apply pre-flight verifies this against the existing archived spec).
  Delete this whole section if no requirements are being modified.
-->

### Requirement: <Existing Title Case Name>

<updated requirement statement (RFC 2119 / BCP 14 keywords)>

<!-- settle: explore/<slug> -->

#### Scenario: <Existing Or New Scenario Name>

- **GIVEN** ...
- **WHEN** ...
- **THEN** ...

<!-- settle: explore/<slug> -->

## REMOVED Requirements

<!-- Delete this whole section if no requirements are being removed. -->

### Requirement: <Title Case Name>

- **Reason**: <why removed>
- **Migration**: <how callers move off it>

<!--
  To rename a requirement, use `## REMOVED Requirements` (with a
  `Migration:` line pointing at the new name) PLUS `## ADDED Requirements`
  for the new name. OpenSpec recognizes only ADDED / MODIFIED / REMOVED.
-->

<!--
BEFORE FINALIZING — run every check.

Syntactic (grep):
- [ ] `grep -nE '\b(should|may)\b' specs/<cap>/spec.md` returns nothing
      (lowercase RFC 2119 keywords don't carry their RFC meaning; use
      MUST/SHALL/SHOULD/MAY uppercase)
- [ ] `grep -nE '^### Scenario:' specs/<cap>/spec.md` returns nothing
      (3 hashtags silently parses as requirement body — scenarios MUST
      use exactly 4 hashtags)
- [ ] Every `### Requirement:` block contains at least one
      `#### Scenario:` heading
- [ ] Every `#### Scenario:` block contains both **WHEN** and **THEN**
- [ ] Requirement headings are Title Case With Spaces (no kebab-case,
      no PascalCase)
- [ ] Every `<!-- settle: explore/<slug> -->` comment points to a
      `### Decision: <slug>` that exists in `explore.md`

For MODIFIED / REMOVED sections (skip if absent):
- [ ] Each `### Requirement:` header is byte-identical (whitespace-
      insensitive) to the existing header in
      `openspec/specs/<cap>/spec.md` — diff after pasting; a mismatch
      silently loses your edits at archive time

Re-classification (re-read each Requirement and ask):
- [ ] "Does this state WHAT the system shall do, or WHY we want it?"
      Rationale and motivation belong in design.md, not in
      requirement prose.
- [ ] "Is this requirement testable as written?" If not — if a tester
      couldn't write a pass/fail assertion from the prose alone —
      sharpen the wording until they can.
-->
