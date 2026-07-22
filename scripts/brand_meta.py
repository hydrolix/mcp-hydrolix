#!/usr/bin/env python3
"""Project brands.toml into shell variables for mcpb/build.sh.

This keeps the mcpb bundle's brand-divergent values sourced from the single
source of truth (brands.toml) instead of a duplicated bash table. It emits
shell-quoted `KEY=value` assignments for the requested brand; build.sh evals
them.

Usage:
    brand_vars="$(python scripts/brand_meta.py [brand])"   # empty -> default
    eval "$brand_vars"

Exits non-zero with a clear message on an unknown brand.
"""

from __future__ import annotations

import json
import shlex
import sys
import tomllib
from pathlib import Path

_BRANDS_TOML = Path(__file__).resolve().parent.parent / "brands.toml"


def main(argv: list[str]) -> int:
    with open(_BRANDS_TOML, "rb") as fh:
        cfg = tomllib.load(fh)
    brands = cfg["brands"]
    brand = (argv[0] if argv else "") or cfg["resolution"]["default"]
    if brand not in brands:
        acceptable = ", ".join(sorted(brands))
        print(
            f"MCP_BRAND={brand!r} is not a valid brand. Valid values: {acceptable}.",
            file=sys.stderr,
        )
        return 1
    b = brands[brand]
    urls = b["urls"]
    out = {
        "MCP_BRAND": brand,
        "DIST_NAME": b["dist_name"],
        "DISPLAY_NAME": b["prose_name"],
        "BRAND_NAME": b["prose_name"],
        "DESCRIPTION": b["mcpb_description"],
        "LONG_DESCRIPTION": b["mcpb_long_description"],
        "AUTHOR_NAME": b["author_name"],
        "AUTHOR_URL": b["author_url"],
        "HOMEPAGE": urls["Home"],
        # Repository pointer: the Source URL when present, else Home.
        "REPOSITORY": urls.get("Source", urls["Home"]),
        "KEYWORDS": json.dumps(b["keywords"]),  # JSON array literal for the manifest
        "ENV_PREFIX": b["env_prefix"],
        "CFG_PREFIX": b["config_prefix"],
        "EXAMPLE_URL": b["example_url"],
    }
    for key, value in out.items():
        print(f"{key}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
