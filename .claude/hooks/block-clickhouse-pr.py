#!/usr/bin/env python3
"""PreToolUse guard: block any Bash invocation that would open a PR against
ClickHouse/mcp-clickhouse (the upstream fork parent of this repo).

This repo is forked from ClickHouse/mcp-clickhouse, so `gh pr create` without
an explicit `--repo` defaults to the upstream parent. PRs from this repo MUST
target hydrolix/mcp-hydrolix. This hook is the hard backstop — it fires before
the Bash tool runs and cannot be bypassed by permission mode (auto, accept-
edits, bypass-permissions all still run PreToolUse hooks).

Exit codes:
  0 — allow
  2 — block, emit message to Claude on stderr
"""

from __future__ import annotations

import json
import re
import sys

FORBIDDEN_REPO = "clickhouse/mcp-clickhouse"
REQUIRED_REPO = "hydrolix/mcp-hydrolix"


def is_pr_create(command: str) -> bool:
    return bool(re.search(r"(?:^|[;&|`$(\s])gh\s+pr\s+create\b", command))


def extract_repo_flag(command: str) -> str | None:
    m = re.search(r"(?:--repo|-R)(?:[=\s]+)(['\"]?)([^'\"\s;|&]+)\1", command)
    return m.group(2).lower() if m else None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0

    command = (payload.get("tool_input") or {}).get("command", "")
    if not isinstance(command, str) or not command:
        return 0

    if not is_pr_create(command):
        return 0

    repo = extract_repo_flag(command)

    if repo is None:
        sys.stderr.write(
            "BLOCKED: `gh pr create` without `--repo` is forbidden in this repo.\n"
            f"This repo is a fork of {FORBIDDEN_REPO}; the default PR target is the\n"
            f"upstream parent, NOT {REQUIRED_REPO}. You must pass `--repo {REQUIRED_REPO}`\n"
            "explicitly. See .claude/hooks/block-clickhouse-pr.py for the rule.\n"
        )
        return 2

    if repo == FORBIDDEN_REPO:
        sys.stderr.write(
            f"BLOCKED: refusing to open a PR against {FORBIDDEN_REPO}.\n"
            f"This repo's PRs must target {REQUIRED_REPO}. Re-run with\n"
            f"`--repo {REQUIRED_REPO}`.\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
