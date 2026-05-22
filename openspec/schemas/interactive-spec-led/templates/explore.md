<!--
  explore.md — audit trail of the interactive Q&A held with the operator
  BEFORE specs, design, and tasks. Resolve ambiguity while change is cheap.

  Hard rules:
  - Only list questions ACTUALLY put to the operator. Not a retrospective notebook.
  - Use design.md "Open Questions" for items that surface later.
  - Decisions are binding constraints on specs, design, and tasks.
  - Pick ONE shape:
    * Default: keep `## Decisions`. The other three sections (Questions Asked,
      Deferred / Out of Scope, Assumptions) are also kept, with `*none*` if empty.
    * Escape hatch: DELETE `## Decisions` and use `## No Ambiguity` instead.
      The other three sections still remain.
-->

*<one-line summary, ≤ 25 words: e.g. "Resolved 3 decisions; 2 assumptions; 1 item deferred.">*

## Questions Asked

<!--
  One bullet per question, paraphrased, in the order asked.
  Write `*none — see No Ambiguity below*` if the escape hatch is in use.
-->

- <question>

## Decisions

<!--
  Pick ONE of two shapes for this section:

  (A) DEFAULT — keep `## Decisions` and DELETE the `## No Ambiguity` stub
      below. One `### Decision: <slug>` block per resolved question.
      Slug is what downstream artifacts cite (`[implements: explore/<slug>]`
      in tasks, `<!-- settle: explore/<slug> -->` in spec requirements).
      **Affects** MUST name a REAL artifact + section the decision binds
      (e.g. `specs/auth/spec.md → Requirement: User Authentication`).
      Placeholder text is rejected by apply pre-flight.

  (B) ESCAPE HATCH — DELETE this whole `## Decisions` section and keep
      only the `## No Ambiguity` block below. Apply pre-flight requires
      the No Ambiguity block to cite an operator confirmation (prompt,
      message, or request that established no ambiguity); self-declared
      no-ambiguity is rejected.

  Never keep both sections.
-->

### Decision: <decision-slug>

- **Question:** <what was asked>
- **Answer:** <operator's resolution>
- **Rationale:** <why this answer; alternatives ruled out>
- **Affects:** <artifact + section, e.g. `specs/<cap>/spec.md → Requirement: <Title Case Name>`>

<!--
## No Ambiguity

USE THIS BLOCK INSTEAD OF `## Decisions` (delete the Decisions section
above and uncomment THIS block). One short paragraph: why the proposal
needed no clarifying questions, plus explicit reference to the
operator's confirmation (cite the prompt or message). MUST be
operator-confirmed; do NOT self-declare. Example: "Change is a
mechanical rename with no behavioral impact; operator confirmed via
AskUserQuestion prompt on YYYY-MM-DD."

Apply pre-flight rejects (a) a No Ambiguity block alongside a live
Decisions block, and (b) a No Ambiguity block with no operator
confirmation cited.
-->

## Deferred / Out of Scope

<!-- Bullets, "<topic> — <why deferred>". Write "*none*" if not applicable. -->

- <topic> — <why deferred>

## Assumptions

<!-- Bullets, "<assumption> — <what breaks if false>". Write "*none*" if not applicable. -->

- <assumption> — <what breaks if false>
