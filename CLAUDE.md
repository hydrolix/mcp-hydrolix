# Claude project rules — mcp-hydrolix

## PRs MUST target hydrolix/mcp-hydrolix

This repository is a fork of `ClickHouse/mcp-clickhouse`. Because of that, `gh
pr create` without an explicit `--repo` flag defaults to opening a PR against
the **upstream parent** (`ClickHouse/mcp-clickhouse`), not this repo. That is
never what we want.

**Rule:** every `gh pr create` invocation in this repo MUST include
`--repo hydrolix/mcp-hydrolix` explicitly. Never open a PR against
`ClickHouse/mcp-clickhouse`.

This rule applies in every permission mode — `default`, `auto`, `acceptEdits`,
`bypassPermissions`, anything else. A `PreToolUse` Bash hook at
`.claude/hooks/block-clickhouse-pr.py` enforces it programmatically (exit code
2 = hard block), and `.claude/settings.json` carries deny rules as a second
layer. Do not disable, weaken, or work around these guards.

## Asking before opening PRs

Opening a pull request is a shared-state action (visible to others, hard to
undo cleanly). Do not run `gh pr create` unless the user has explicitly asked
for a PR in this turn. Committing locally and pushing to a branch is fine when
the user asks; opening the PR is a separate authorization.
