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

  Test-task rule: for every `#### Scenario:` in your specs, schedule
  EXACTLY ONE task here. Two parts:
  - `[implements: <capability-folder>/<requirement-slug>, meta/tests]`
    cites the PARENT requirement (not the scenario).
  - `verify:` names the SCENARIO-specific test function.
  A requirement with N scenarios produces N test tasks, each verifying
  a distinct `test_<scenario_slug>` function. Apply pre-flight rejects
  scenarios with no matching verify clause.

  Test naming convention (for verify: clauses):
  - File: `tests/test_<capability_folder>.py` (apply slug rule to the
    capability folder name, then `-` → `_` for the filename).
  - Function: `test_<scenario_slug>` — apply slug rule to the scenario
    heading text, then `-` → `_` (Python identifiers can't contain `-`).
    So scenario `Parses Valid Url` → `parses-valid-url` (kebab slug) →
    `test_parses_valid_url` (test function).


  Separator convention: put ` — ` (space, em-dash, space) between the
  `[implements: ...]` block and the `verify:` clause. Apply pre-flight
  finds verify by the literal token `verify:` regardless of separator,
  but the em-dash form is what reviewers expect.

  Task states (valid checkbox forms; opsx:apply maintains them):
  - `- [ ]` open / not started
  - `- [x]` complete and verify passed
  - `- [-]` complete-but-verify-deferred (verify could not run in the
    apply environment; the limitation is reported at post-execution).

  Anti-patterns:
  - Tasks without a verify clause.
  - Prose paragraphs between bullets.
  - Tasks that bundle multiple deliverables (split them).
  - Tasks with no `[implements: ...]` citation.
  - Citing a requirement with a slug that doesn't match the kebab-derived
    form of the heading (use the slug rule, not the raw heading text).
  - Citing `meta/<kind>` with a `<kind>` outside `tests`, `docs`,
    `migration`, `rollout`, `tooling` (apply pre-flight rejects others).
  - Bundling N scenarios under one test task (apply pre-flight rejects
    scenarios with no matching verify clause).

  Phases are descriptive — use as many or as few as the work needs. The
  layout below is illustrative.
-->

*<one-line summary, ≤ 25 words: e.g. "3 phases, 11 tasks; ends with rollout gate.">*

## 1. <phase name>

- [ ] 1.1 <imperative verb>: <concise deliverable> [implements: <capability-folder>/<requirement-slug>] — verify: <check>
- [ ] 1.2 <task> [implements: design/<decision-slug>] — verify: <check>

## 2. <phase name>

- [ ] 2.1 <task> [implements: explore/<decision-slug>] — verify: <check>
- [ ] 2.2 Add test for scenario `<Title Case Scenario Name>` [implements: <capability-folder>/<requirement-slug>, meta/tests] — verify: `pytest -q tests/test_<capability_folder>.py::test_<scenario_slug>` green (function name = slug of the scenario heading; one test task per scenario, all citing the same requirement-slug)

## 3. <phase name>

- [ ] 3.1 <docs / migration / rollout task> [implements: meta/<kind>] — verify: <check>
