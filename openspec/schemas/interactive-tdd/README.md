# Interactive TDD for OpenSpec

A portable schema combining dependency-aware discovery, shared vocabulary,
explicit testing seams, behavior slices, TDD, and standards/spec review.
The whole directory is the distribution unit. It can live in any repository;
it has no dependency on the repository that hosts this copy.

## Install and select

Requires OpenSpec with custom schemas. Tested against the installed OpenSpec
1.13.0 CLI. Behavior-neutral changes require its `skip_specs` metadata support;
run the smoke test against your own CLI rather than relying on a version alone.
Python and uv are only needed for the installer and smoke test, not for using
the schema. The target project can use any language or test runner.

From this directory, install for the current user:

```sh
uv run --no-project python scripts/install.py
```

The installer copies this directory to the OpenSpec user data directory:
`$XDG_DATA_HOME/openspec/schemas/interactive-tdd`, otherwise
`~/.local/share/openspec/schemas/interactive-tdd` on Unix/macOS, or
`%LOCALAPPDATA%/openspec/schemas/interactive-tdd` on Windows. It is idempotent
for identical contents and refuses to overwrite a differing installation.
For an update, review the diff, move the existing directory to a backup outside
`schemas/`, and reinstall. Installed copies do not update automatically.

For team use, copy this directory into the destination project's
`openspec/schemas/interactive-tdd/` and commit it there. Project-local schemas
take precedence over user-level copies of the same name.

From the destination project (or selected standalone OpenSpec store):

```sh
openspec schema which interactive-tdd --json
openspec schema validate interactive-tdd --json
openspec new change implement-feature --schema interactive-tdd
openspec status --change implement-feature --json
openspec instructions proposal --change implement-feature --json
```

Preserve `--store <id>` on commands that accept it when using a selected store.
For schema commands, run from the resolved planning root. To use this workflow
by default, set the existing `schema` field in `openspec/config.yaml` to
`interactive-tdd`, preserving other fields. Existing change metadata retains
its selected schema; do not migrate in-flight changes implicitly.

## Workflow and ownership

```text
proposal -> explore -> specs -> design -> tasks -> apply -> review -> archive
                                            red -> green per behavior slice
```

OpenSpec artifacts are authoritative for scope, decisions, scenarios, and work.
The glossary defines current domain terms across changes. Use a project's
existing glossary convention, otherwise lazily create `CONTEXT.md` in the target
code root. Proposed terms stay in the change until implemented; glossary
promotion is a checked task. This package ships no project-specific glossary.

Pocock skills are optional helpers: `grilling` for dependent decisions,
`domain-modeling` for vocabulary, `codebase-design` for interfaces, `tdd` for
behavioral tests, `diagnosing-bugs` for unexpected failures, and `code-review`
for review. The essential behavior is in schema instructions, so skill names,
installation paths, issue trackers, and particular assistant commands are not
runtime dependencies. When using a helper, follow the schema's output contract
and applicable project/user instructions. Reuse explicit prior seam agreements.

The discovery step asks one decision question at a time by default. It preserves
decision identifiers and downstream citations. It does not launch a second
interview, PRD, issue-publishing flow, or ADR tree.

Each TDD task owns its failing test AND passing implementation. Multiple related
scenarios may share a task, with one red/green cycle at a time. The schema
defines exact scenario identities so coverage remains traceable. Direct-check
tasks cover documentation and behavior-neutral work; behavior-changing exceptions
need a cited user decision. Existing correct coverage does not require an
invented failing test.

## Execution evidence and review

During apply create `evidence.md` beside `tasks.md` using this structure per task:

```markdown
## Task 1.1

- Scenario: <full scenario identity>
- Seam and test: <agreed seam; executable test identifier>
- Working directory: <target project directory>
- Red: <exact command, exit status, intended assertion failure>
- Green: <exact command, exit status, observed result>
- Verify: <task command and observed result>
- Limitations: <remaining limitation or none>
```

For existing coverage or check-mode tasks, replace Red with the actual rationale.
Never prefill execution claims from the plan. Keep failed or unavailable checks
unchecked in tasks.md; do not count deferred verification as completion.

Review is an artifact outside `apply.requires`, so planning can finish without
pretending implementation was reviewed. Its instruction limits generation to
post-implementation. A final check-mode task tracks review completion, keeping
CLI progress incomplete until review and required reruns are done. Apply
explicitly requests the review instructions:

```sh
openspec instructions review --change implement-feature --json
```

The reviewer checks the actual diff against project standards and the selected
change's specs, and records those findings separately. A generic review helper
must use those explicit artifact paths instead of inferring an issue tracker.

OpenSpec validates schema structure and tracks file/checklist state. This schema
adds agent instructions for citation checks, semantic scenario coverage, red/green
evidence, and review. These are NOT new CLI-enforced gates. A review file, a green
structural validator, or CLI `all_done` is not proof of correctness. Review must
distinguish reported execution from independently rerun checks. Archive remains
an explicitly authorized action after verification and review.

## Validate and distribute

```sh
uv run --no-project python scripts/smoke.py
```

The smoke test uses a temporary project and isolated OpenSpec configuration/data.
It exercises schema loading, instructions, missing-artifact blocking, checklist
progress, post-implementation review availability, behavior-neutral skip metadata,
and a real illustrative red/green cycle. It also tests installation resolution
and refusal to overwrite differing contents. The Python example tests the
workflow mechanics, not any target application's behavior or an agent's adherence.

Copy or zip this entire directory to share it. To remove the user installation,
remove only its `interactive-tdd` directory; project-local copies remain available.
Migrate an old change only with explicit scope: preserve decision identifiers,
map every scenario to a slice, agree seams, reconcile evidence and tasks, and
then change that change's schema metadata. Never rewrite past evidence.

## Attribution

Workflow techniques draw on [Matt Pocock's composable engineering skills](https://github.com/mattpocock/skills)
and [OpenSpec's custom schema mechanism](https://github.com/Fission-AI/OpenSpec/blob/main/docs/customization.md).
This is an independently authored integration, not an upstream OpenSpec feature
or a vendored copy of the Pocock skill collection.
