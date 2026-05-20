<!--
  tasks.md — the /opsx:apply runbook. Dependency-ordered, traceable, verifiable.

  Required per task:
  - At least one `[implements: ...]` citation:
    - `[implements: <capability-folder>/<requirement-slug>]` — slug derived
      from the requirement heading: lowercase, spaces → `-`, strip
      `[^a-z0-9-]`. So heading `### Requirement: Url Parsing` → `url-parsing`.
    - `[implements: design/<decision-slug>]` — slug after `Decision: ` in design.md.
    - `[implements: explore/<decision-slug>]` — slug after `Decision: ` in explore.md.
    - `[implements: meta/<kind>]` where <kind> ∈ tests, docs, migration, rollout, tooling
  - `verify: <concrete check>` clause (scenario name, test command, lint, etc.).

  Test-task rule: for every `#### Scenario:` in your specs, schedule at
  least one task here that adds/updates a test for it, citing
  `[implements: <capability-folder>/<requirement-slug>, meta/tests]`
  (requirement-slug = kebab-slug of the parent requirement's heading; NOT
  the scenario slug).

  Test naming convention (for verify: clauses):
  - File: `tests/test_<capability-folder>.py` with `-` → `_`.
  - Function: `test_<scenario-slug>` (kebab-case of scenario name).


  Anti-patterns:
  - Tasks without a verify clause.
  - Prose paragraphs between bullets.
  - Tasks that bundle multiple deliverables (split them).
  - Tasks with no `[implements: ...]` citation.
  - Citing a requirement with a slug that doesn't match the kebab-derived
    form of the heading (use the slug rule, not the raw heading text).

  Phases are descriptive — use as many or as few as the work needs. The
  layout below is illustrative.
-->

*<one-line summary, ≤ 25 words: e.g. "3 phases, 11 tasks; ends with rollout gate.">*

## 1. <phase name>

- [ ] 1.1 <imperative verb>: <concise deliverable> [implements: <capability-folder>/<requirement-slug>] — verify: <check>
- [ ] 1.2 <task> [implements: design/<decision-slug>] — verify: <check>

## 2. <phase name>

- [ ] 2.1 <task> [implements: explore/<decision-slug>] — verify: <check>
- [ ] 2.2 Add test for scenario `<Title Case Scenario Name>` [implements: <capability-folder>/<requirement-slug>, meta/tests] — verify: `pytest -q tests/test_<capability_folder>.py::test_<scenario_slug>` green

## 3. <phase name>

- [ ] 3.1 <docs / migration / rollout task> [implements: meta/<kind>] — verify: <check>
