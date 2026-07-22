#!/usr/bin/env python3
"""Brand-aware build wrapper: ``uv build`` + out-of-backend brand rename.

Why this exists: uv/PEP 621 require a static ``project.name``, so the build
backend always emits ``mcp-hydrolix``-named artifacts. Their *contents* are
already brand-correct (the metadata hook in ``hatch_build.py`` sets
description/scripts/urls/readme and bakes ``_brand.py`` per ``MCP_BRAND``), but
the distribution *name* -- the ``.dist-info`` dir, the ``Name`` field, and the
filename -- can only be changed after the backend returns, because the frontend
verifies the returned filename exists. This wrapper does exactly that.

Isolation matters: because the backend emits ``mcp-hydrolix``-named files for
*both* brands, a TrafficPeak build MUST NOT share an output directory with a
Hydrolix build mid-flight -- otherwise the TP ``uv build`` would overwrite the
Hydrolix-named artifacts with TP content before the rename runs. This wrapper
therefore always builds into a private temp dir and moves the *renamed*
artifacts into the target dir, so it can never clobber a paired Hydrolix build.

Usage (equivalent to ``uv build`` but brand-correct):

    MCP_BRAND=trafficpeak python scripts/brand_build.py [uv build args...]
    MCP_BRAND=hydrolix    python scripts/brand_build.py            # == uv build

Extra args are forwarded to ``uv build`` (e.g. ``--wheel``, ``--sdist``). Any
caller-supplied ``--out-dir``/``-o`` is honored as the *final* destination but
stripped from the uv invocation (which uses the private temp dir).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# hatch_build.py lives at the repo root, one level up from scripts/.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from hatch_build import rebrand_artifact, selected_brand  # noqa: E402


def _split_out_dir(uv_args: list[str]) -> tuple[Path, list[str]]:
    """Return (final destination dir, uv args with any --out-dir/-o removed)."""
    dest = _REPO_ROOT / "dist"
    passthrough: list[str] = []
    i = 0
    while i < len(uv_args):
        arg = uv_args[i]
        if arg in ("-o", "--out-dir") and i + 1 < len(uv_args):
            dest = Path(uv_args[i + 1])
            i += 2
            continue
        if arg.startswith("--out-dir="):
            dest = Path(arg.split("=", 1)[1])
            i += 1
            continue
        passthrough.append(arg)
        i += 1
    return dest, passthrough


def main(argv: list[str]) -> int:
    brand = selected_brand()  # validates MCP_BRAND, raises on invalid value
    dest, passthrough = _split_out_dir(argv)
    dest.mkdir(parents=True, exist_ok=True)

    # Build into a private temp dir so we never collide with (or clobber)
    # artifacts already in `dest` -- notably the paired Hydrolix build.
    with tempfile.TemporaryDirectory(prefix="mcp_brand_build_") as staging:
        result = subprocess.run(["uv", "build", *passthrough, "--out-dir", staging], cwd=_REPO_ROOT)
        if result.returncode != 0:
            return result.returncode

        for artifact in sorted(Path(staging).glob("*")):
            if not artifact.name.endswith((".whl", ".tar.gz")):
                continue
            renamed = rebrand_artifact(artifact, brand)  # no-op for hydrolix
            final = dest / renamed.name
            shutil.move(str(renamed), str(final))
            print(f"Brand build ({brand}): {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
