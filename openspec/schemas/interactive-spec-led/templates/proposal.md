<!--
  proposal.md — WHY this change exists. ≤ 1 page (≈ 300 words).
  Do NOT include implementation steps, design rationale, or background recap.
  Run `ls openspec/specs/` before filling in Capabilities; reuse exact folder names.
-->

*<one-line summary, ≤ 25 words: what this change is, in a single sentence a reviewer can skim>*

## Why

<!-- ≤ 60 words, 1-2 sentences. The problem (or opportunity) and why now. No background recap. -->

## What Changes

<!--
  ≤ 8 bullets. Each bullet is a concrete capability addition, modification, or
  removal. Mark breaking changes with **BREAKING**.
-->

- <change>

## Capabilities

<!--
  Load-bearing section. Every name here MUST map 1:1 to a specs/<name>/spec.md
  in this change. Implementation-only changes (no requirement change) do NOT
  belong under Modified.
-->

### New

- `<kebab-case-name>` — <≤ 15 word description; becomes specs/<name>/spec.md>

### Modified

<!-- Use EXACT folder names from openspec/specs/. Write "*none*" if no requirements change. -->

- `<existing-name>` — <which requirement is changing>

## Impact

<!-- One bullet each: affected code paths, public APIs, external dependencies, data migrations. -->

- <impact>

<!--
BEFORE FINALIZING — run every check; the artifact is not done until each is satisfied.

Syntactic (grep / wc):
- [ ] `grep -E 'LOC|line[s]? of code|~[0-9]+ lines|≈ ?[0-9]+ lines'` returns nothing
- [ ] No backtick-quoted env-var assignments (`FOO=bar`) anywhere
- [ ] No code fences (```)
- [ ] `wc -w < proposal.md` ≤ 300
- [ ] What Changes bullet count ≤ 8
- [ ] Every capability under `### New` has a corresponding `specs/<name>/spec.md` in this change

Re-classification (re-read each bullet and ask):
- [ ] For each What Changes bullet: "does this describe an observable
      capability change, or how we implement it?" If implementation,
      move to design.md Decisions and rewrite the bullet at capability level.
- [ ] For each Impact bullet: "does this name what's touched (file/system),
      or how it's changed (mechanism)?" If mechanism, simplify to the
      file/system; the mechanism goes in design.md.
-->
