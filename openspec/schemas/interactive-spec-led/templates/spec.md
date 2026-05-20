<!--
  spec.md — WHAT the system shall do, in requirement-style (RFC 2119 /
  BCP 14: MUST, SHALL, SHOULD, MAY), testable form.

  Headers (silent-failure traps; the formatter is strict):
  - `## ADDED | MODIFIED | REMOVED | RENAMED Requirements`
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

  HARD RULE for MODIFIED requirements:
    Header line MUST be byte-identical (whitespace-insensitive) to the
    existing header in openspec/specs/<cap>/spec.md. Mismatch silently
    loses your edits at archive time. Diff after pasting.

  Style: SHALL / MUST; never should / may. Every requirement has ≥ 1 scenario.

  This template shows all four delta sections. Delete the sections that
  don't apply to this change rather than commenting them out.

  Tracing explore Decisions: add `<!-- settle: explore/<slug> -->` on its
  own line immediately under any requirement or scenario heading that
  implements an explore decision.

  Anti-patterns:
  - `should` / `may` (use SHALL / MUST).
  - Scenario with WHEN but no THEN (or vice versa).
  - Requirement with zero scenarios.
  - Title-Case-With-Spaces-Wrong-Form (e.g. `kebab-case` or `PascalCase`
    requirement headings; OpenSpec archive expects Title Case With Spaces).
  - MODIFIED block header that doesn't byte-match the existing spec.
-->

*<one-line summary, ≤ 25 words: what this capability covers>*

## ADDED Requirements

### Requirement: <Title Case Name>
<!-- settle: explore/<slug> -->

<!-- One-sentence requirement statement using RFC 2119 / BCP 14 keywords (prefer MUST / SHALL). -->

#### Scenario: <Short Scenario Name>

- **GIVEN** <precondition state, optional>
- **WHEN** <trigger event>
- **THEN** <observable outcome>
- **AND** <additional outcome, optional>

## MODIFIED Requirements

<!--
  Copy the ENTIRE existing requirement block (header + every scenario) from
  openspec/specs/<cap>/spec.md, then edit. Header MUST be byte-identical.
-->

### Requirement: <Existing Title Case Name>

<updated requirement statement (RFC 2119 / BCP 14 keywords)>

#### Scenario: <Existing Or New Scenario Name>

- **GIVEN** ...
- **WHEN** ...
- **THEN** ...

## REMOVED Requirements

### Requirement: <Title Case Name>

- **Reason**: <why removed>
- **Migration**: <how callers move off it>

## RENAMED Requirements

- FROM: `<Old Title Case Name>`
- TO: `<New Title Case Name>`
