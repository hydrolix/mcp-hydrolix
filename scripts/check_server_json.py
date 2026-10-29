#!/usr/bin/env python3
"""Fail unless server.json is publishable to the MCP registry as committed.

publish.yml hands server.json to the MCP registry exactly as committed, so it
must carry the version PyPI receives (pyproject.toml) as its top-level version
and every package version, and must validate against the schema its $schema
field names. bump-version keeps the versions in sync; this catches a hand edit
that drifted or broke the schema. Run on every PR (tests.yaml) and before any
release publish (build-release-artifacts.yml).

The schema is downloaded from its $schema URL, so this needs network access
and the jsonschema package.

Usage:
    uv run --no-project --with 'jsonschema>=4,<5' \
        python scripts/check_server_json.py [repo_root]   # default: this repo
"""

from __future__ import annotations

import json
import sys
import tomllib
import urllib.request
from pathlib import Path

import jsonschema

_REPO_ROOT = Path(__file__).resolve().parent.parent


def version_errors(server: dict, expected: str) -> list[str]:
    found = {"version": server["version"]}
    for i, pkg in enumerate(server["packages"]):
        found[f"packages[{i}].version"] = pkg["version"]
    return [
        f"{field} is {value!r}, but pyproject.toml version is {expected!r}"
        for field, value in found.items()
        if value != expected
    ]


def schema_errors(server: dict) -> list[str]:
    with urllib.request.urlopen(server["$schema"], timeout=30) as resp:
        schema = json.load(resp)
    validator = jsonschema.validators.validator_for(schema)(schema)
    return [
        f"{'/'.join(map(str, err.absolute_path)) or '<root>'}: {err.message}"
        for err in validator.iter_errors(server)
    ]


def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else _REPO_ROOT
    with open(root / "pyproject.toml", "rb") as fh:
        expected = tomllib.load(fh)["project"]["version"]
    server = json.loads((root / "server.json").read_text(encoding="utf-8"))
    errors = version_errors(server, expected) + schema_errors(server)
    for error in errors:
        print(f"server.json: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
