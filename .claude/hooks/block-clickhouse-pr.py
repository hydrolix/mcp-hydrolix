#!/usr/bin/env python3
"""PreToolUse guard: block any invocation that would open a PR against
ClickHouse/mcp-clickhouse (the upstream fork parent of this repo).

Covers two surfaces:

1. Bash — `gh pr create` without `--repo`, or with `--repo`/`-R` pointing at
   the upstream parent. Without `--repo`, `gh` defaults to the parent fork.

2. MCP — any tool whose name ends in `create_pull_request` (github MCP
   servers expose this; both the official `mcp__github__create_pull_request`
   and the ECC plugin's `mcp__plugin_ecc_github__create_pull_request`
   accept `owner`/`repo` parameters).

PreToolUse hooks fire before the tool runs and cannot be bypassed by
permission mode (default / auto / acceptEdits / bypassPermissions all run
PreToolUse hooks).

Exit codes:
  0 — allow
  2 — block, emit message to Claude on stderr
"""

from __future__ import annotations

import json
import re
import sys

FORBIDDEN_OWNER = "clickhouse"
FORBIDDEN_REPO = "mcp-clickhouse"
FORBIDDEN_SLUG = f"{FORBIDDEN_OWNER}/{FORBIDDEN_REPO}"
REQUIRED_SLUG = "hydrolix/mcp-hydrolix"


def is_pr_create(command: str) -> bool:
    return bool(re.search(r"(?:^|[;&|`$(\s])gh\s+pr\s+create\b", command))


def extract_repo_flag(command: str) -> str | None:
    m = re.search(r"(?:--repo|-R)(?:[=\s]+)(['\"]?)([^'\"\s;|&]+)\1", command)
    return m.group(2).lower() if m else None


def handle_bash(tool_input: dict) -> int:
    command = tool_input.get("command", "")
    if not isinstance(command, str) or not command:
        return 0
    if not is_pr_create(command):
        return 0

    repo = extract_repo_flag(command)

    if repo is None:
        sys.stderr.write(
            "BLOCKED: `gh pr create` without `--repo` is forbidden in this repo.\n"
            f"This repo is a fork of {FORBIDDEN_SLUG}; the default PR target is the\n"
            f"upstream parent, NOT {REQUIRED_SLUG}. You must pass `--repo {REQUIRED_SLUG}`\n"
            "explicitly. See .claude/hooks/block-clickhouse-pr.py for the rule.\n"
        )
        return 2

    if repo == FORBIDDEN_SLUG:
        sys.stderr.write(
            f"BLOCKED: refusing to open a PR against {FORBIDDEN_SLUG}.\n"
            f"This repo's PRs must target {REQUIRED_SLUG}. Re-run with\n"
            f"`--repo {REQUIRED_SLUG}`.\n"
        )
        return 2

    return 0


def handle_mcp_pr_create(tool_name: str, tool_input: dict) -> int:
    owner = str(tool_input.get("owner", "")).lower()
    repo = str(tool_input.get("repo", "")).lower()

    if owner == FORBIDDEN_OWNER and repo == FORBIDDEN_REPO:
        sys.stderr.write(
            f"BLOCKED: refusing to open a PR against {FORBIDDEN_SLUG} via {tool_name}.\n"
            f"This repo's PRs must target {REQUIRED_SLUG}. Re-call with\n"
            f"owner='hydrolix', repo='mcp-hydrolix'.\n"
        )
        return 2

    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    if tool_name == "Bash":
        return handle_bash(tool_input)

    if tool_name.startswith("mcp__") and tool_name.endswith("create_pull_request"):
        return handle_mcp_pr_create(tool_name, tool_input)

    return 0


if __name__ == "__main__":
    sys.exit(main())
