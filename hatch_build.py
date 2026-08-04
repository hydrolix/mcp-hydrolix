"""Custom Hatchling hooks that bake brand identity into the built distribution.

``MCP_BRAND`` selects the brand (``hydrolix`` | ``trafficpeak``, default
``hydrolix``). Two distributions -- ``mcp-hydrolix`` and ``mcp-trafficpeak`` --
ship from this single source tree at the same version, differing only in
build-time branding.

Because ``uv`` / PEP 621 require a *static* ``project.name`` (a dynamic or
``{env:...}`` name is rejected before the backend runs), the distribution name
cannot be flipped through ordinary metadata. Instead:

  * ``BrandMetadataHook`` populates the brand-varying PEP 621 fields that CAN be
    dynamic -- ``description``, ``scripts``, ``urls``, ``readme`` (the PyPI
    long-description) -- for BOTH brands from the single ``BRANDS`` table. The
    long description is this repo's ``README.md`` run through a
    brand-substitution filter (identity transform in Hydrolix mode).
  * ``BrandBuildHook`` bakes ``mcp_hydrolix/_brand.py`` (the runtime brand
    constants) into the artifact, and for the ``trafficpeak`` brand repackages
    the finished wheel + sdist under the ``mcp-trafficpeak`` name -- renaming the
    ``.dist-info`` / sdist top directory, patching the ``Name`` field in
    METADATA / PKG-INFO, rebuilding ``RECORD``, and renaming the artifact file.

The Python import path ``mcp_hydrolix`` is intentionally NOT renamed; both
wheels import the same module.

Inspect what a built wheel actually baked::

    unzip -p dist/*.whl '*/METADATA'
    unzip -p dist/*.whl 'mcp_hydrolix/_brand.py'
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import tarfile
import tempfile
import tomllib
from pathlib import Path
from typing import Any

# Hatchling is only present in the isolated build backend. The out-of-backend
# wrapper (scripts/brand_build.py) and the tests import this module purely for
# its brand table and rebrand helpers, so fall back to a plain base class when
# Hatchling is absent -- the hook subclasses are simply never used in that case.
try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
    from hatchling.metadata.plugin.interface import MetadataHookInterface
except ImportError:  # pragma: no cover - exercised only outside the build env
    BuildHookInterface = object  # type: ignore[assignment,misc]
    MetadataHookInterface = object  # type: ignore[assignment,misc]

ENTRY_POINT = "mcp_hydrolix.main:main"
BRAND_ENV_VAR = "MCP_BRAND"

# brands.toml (adjacent to this file) is the SINGLE SOURCE OF TRUTH for every
# brand-divergent value. Loaded relative to this file so it resolves regardless
# of the caller's cwd (build backend, the brand-build wrapper, tests). New
# brand-divergent config MUST go in brands.toml -- never re-declared here or in
# mcpb/build.sh / the release workflow.
_BRANDS_TOML = Path(__file__).resolve().parent / "brands.toml"
with open(_BRANDS_TOML, "rb") as _f:
    _CONFIG = tomllib.load(_f)

BRANDS: dict[str, dict[str, Any]] = _CONFIG["brands"]
DEFAULT_BRAND: str = _CONFIG["resolution"]["default"]
_PRECEDENCE: list[str] = _CONFIG["resolution"]["precedence"]
_EXEMPT_ORG_TOKENS: tuple[str, ...] = tuple(_CONFIG["filter"]["exempt_org_tokens"])


def selected_brand() -> str:
    """Return the validated ``MCP_BRAND`` value, or raise with a clear message."""
    raw = os.environ.get(BRAND_ENV_VAR, DEFAULT_BRAND)
    if raw not in BRANDS:
        acceptable = ", ".join(sorted(BRANDS))
        raise ValueError(
            f"{BRAND_ENV_VAR}={raw!r} is not a valid brand. "
            f"Set {BRAND_ENV_VAR} to one of: {acceptable} (default: {DEFAULT_BRAND})."
        )
    return raw


def rebrand_text(text: str, brand: str) -> str:
    """Rebrand README / long-description PROSE for the target brand.

    Identity transform in Hydrolix mode. For any other brand, EVERY occurrence
    of the Hydrolix name is replaced (case-insensitively), preserving each
    match's casing pattern -- so ``mcp-hydrolix``, ``HYDROLIX_URL``,
    ``Hydrolix``, ``hydrolix.live``, the ``mcp--hydrolix`` shields badges, and
    lowercase ``hydrolix_*`` config keys all rebrand. Customer-facing prose MUST
    never mention the other brand. The hydrolix org that legitimately appears in
    repository URLs is tolerated ONLY in structured manifest / metadata fields
    (set from the BRANDS ``urls`` table and ``mcpb/build.sh``) -- never through
    this prose filter, so those pointers are unaffected here.
    """
    if brand == "hydrolix":
        return text
    prose = BRANDS[brand]["prose_name"]

    # GitHub-org identity namespaces are exempt: they name the *owning org*
    # (hydrolix) -- a structured ownership identity, not brand prose -- so they
    # survive the scrub. Any package segment after them still rebrands, e.g.
    # `io.github.hydrolix/mcp-hydrolix` -> `io.github.hydrolix/mcp-trafficpeak`.
    # Protected by placeholder (which contains no "hydrolix") across the scrub.
    guard = {f"\x00EXEMPT{i}\x00": tok for i, tok in enumerate(_EXEMPT_ORG_TOKENS)}
    for placeholder, tok in guard.items():
        text = text.replace(tok, placeholder)

    def _sub(match: "re.Match[str]") -> str:
        s = match.group(0)
        if s.isupper():
            return prose.upper()
        if s[0].isupper():
            return prose
        return prose.lower()

    text = re.sub("hydrolix", _sub, text, flags=re.IGNORECASE)
    for placeholder, tok in guard.items():
        text = text.replace(placeholder, tok)
    return text


def brand_module_source(brand: str) -> str:
    """Return the source of the ``mcp_hydrolix/_brand.py`` module for ``brand``.

    Bakes the runtime-relevant subset of brands.toml (this brand's id, dist name,
    and own env prefix, plus the global dual-namespace precedence) so mcp_env.py
    reads them at runtime without needing brands.toml (which is not shipped).
    """
    cfg = BRANDS[brand]
    precedence = tuple(BRANDS[b]["env_prefix"] for b in _PRECEDENCE)
    return (
        '"""Build-time-baked brand identity. Generated by hatch_build.py.\n\n'
        "Do not edit by hand -- the committed copy holds the Hydrolix defaults\n"
        'and the Hatchling hook overwrites this at build time per MCP_BRAND."""\n\n'
        f'__brand__ = "{cfg["brand"]}"\n'
        f'__dist_name__ = "{cfg["dist_name"]}"\n'
        f'__env_prefix__ = "{cfg["env_prefix"]}"\n'
        f"__env_prefix_precedence__ = {precedence!r}\n"
    )


class BrandMetadataHook(MetadataHookInterface):
    """Populate the brand-varying dynamic PEP 621 fields from the BRANDS table."""

    def update(self, metadata: dict[str, Any]) -> None:
        brand = selected_brand()
        cfg = BRANDS[brand]
        metadata["description"] = cfg["summary"]
        metadata["scripts"] = {cfg["dist_name"]: ENTRY_POINT}
        metadata["urls"] = dict(cfg["urls"])
        readme = (Path(self.root) / "README.md").read_text(encoding="utf-8")
        metadata["readme"] = {
            "content-type": "text/markdown",
            "text": rebrand_text(readme, brand),
        }


class BrandBuildHook(BuildHookInterface):
    """Bake ``_brand.py`` into the artifact and repackage TP builds by name."""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        brand = selected_brand()
        # Generate the brand module to a temp file and force-include it at the
        # package path, overriding the committed (Hydrolix-default) source copy,
        # which pyproject excludes from collection. This keeps the source tree
        # unmutated (dev / editable installs keep the committed defaults).
        fd, tmp = tempfile.mkstemp(prefix="mcp_brand_", suffix=".py")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(brand_module_source(brand))
        self._brand_tmp = tmp
        build_data.setdefault("force_include", {})[tmp] = "mcp_hydrolix/_brand.py"

    def finalize(self, version: str, build_data: dict[str, Any], artifact_path: str) -> None:
        # NOTE: the artifact is NOT renamed here. A PEP 517 frontend (uv, build)
        # verifies that the filename the backend returns exists on disk, so
        # renaming the artifact inside the backend makes `uv build` fail its
        # post-condition even though the file is correct. The mcp-trafficpeak
        # rename is therefore applied by the out-of-backend wrapper
        # scripts/brand_build.py, which calls rebrand_artifact() below.
        tmp = getattr(self, "_brand_tmp", None)
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)


# --- repackaging helpers ---------------------------------------------------

_OLD_DIST = "mcp-hydrolix"
_OLD_UNDER = "mcp_hydrolix"


def _dist_underscore(dist_name: str) -> str:
    return dist_name.replace("-", "_")


def _patch_name_field(text: str, new_dist: str) -> str:
    """Rewrite the ``Name:`` header line in METADATA / PKG-INFO."""
    return re.sub(rf"(?m)^Name: {re.escape(_OLD_DIST)}$", f"Name: {new_dist}", text)


def _record_bytes(members: dict[str, bytes], record_path: str) -> bytes:
    """Build a wheel RECORD file for ``members`` (RECORD's own line has no hash).

    Emitted with ``csv.writer`` so paths containing commas/quotes are correctly
    quoted per the RECORD (RFC 4180) format.
    """
    import csv
    import io as _io

    buf = _io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for name, data in members.items():
        if name == record_path:
            writer.writerow([name, "", ""])
            continue
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([name, f"sha256={digest}", len(data)])
    return buf.getvalue().encode("utf-8")


def _rebrand_wheel(path: Path, new_dist: str) -> None:
    """Repackage a wheel under ``new_dist``: rename dist-info, patch Name, rebuild RECORD."""
    import zipfile

    new_under = _dist_underscore(new_dist)
    with zipfile.ZipFile(path) as z:
        members = {n: z.read(n) for n in z.namelist()}

    out: dict[str, bytes] = {}
    for name, data in members.items():
        # Only the ".dist-info" directory carries the hyphen+version prefix;
        # the package directory "mcp_hydrolix/" (no hyphen) is left untouched.
        new_name = name
        if name.startswith(f"{_OLD_UNDER}-"):
            new_name = new_under + name[len(_OLD_UNDER) :]
        if new_name.endswith(".dist-info/METADATA"):
            data = _patch_name_field(data.decode("utf-8"), new_dist).encode("utf-8")
        out[new_name] = data

    record_path = next(n for n in out if n.endswith(".dist-info/RECORD"))
    out[record_path] = _record_bytes(out, record_path)

    new_path = path.with_name(path.name.replace(f"{_OLD_UNDER}-", f"{new_under}-", 1))
    with zipfile.ZipFile(new_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in out.items():
            z.writestr(name, data)
    if new_path != path:
        path.unlink()
    return new_path


def _rebrand_sdist(path: Path, new_dist: str) -> None:
    """Repackage an sdist under ``new_dist``: rename top dir, patch PKG-INFO Name."""
    new_under = _dist_underscore(new_dist)
    old_prefix = f"{_OLD_UNDER}-"
    new_path = path.with_name(path.name.replace(old_prefix, f"{new_under}-", 1))

    with tarfile.open(path, "r:gz") as tin:
        infos = tin.getmembers()
        payloads = {m.name: (tin.extractfile(m).read() if m.isfile() else None) for m in infos}

    with tarfile.open(new_path, "w:gz") as tout:
        for m in infos:
            new_name = m.name
            if m.name.startswith(old_prefix):
                new_name = new_under + m.name[len(_OLD_UNDER) :]
            data = payloads[m.name]
            if data is not None and new_name.endswith("/PKG-INFO"):
                data = _patch_name_field(data.decode("utf-8"), new_dist).encode("utf-8")
            m.name = new_name
            if data is None:
                tout.addfile(m)
            else:
                m.size = len(data)
                tout.addfile(m, io.BytesIO(data))
    if new_path != path:
        path.unlink()
    return new_path


def rebrand_artifact(artifact_path: str | Path, brand: str) -> Path:
    """Rename a Hydrolix-built artifact to ``brand``'s distribution name.

    Applied by the out-of-backend wrapper (scripts/brand_build.py) after
    ``uv build`` produces the Hydrolix-named wheel/sdist (whose *contents* are
    already brand-correct via the metadata hook). No-op for the Hydrolix brand.
    Returns the resulting path.
    """
    path = Path(artifact_path)
    if brand == "hydrolix":
        return path
    dist_name = BRANDS[brand]["dist_name"]
    if path.name.endswith(".whl"):
        return _rebrand_wheel(path, dist_name)
    if path.name.endswith(".tar.gz"):
        return _rebrand_sdist(path, dist_name)
    return path
