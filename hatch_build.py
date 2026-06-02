"""Build-time brand selection for the mcp-hydrolix / mcp-trafficpeak distributions.

This Hatchling build hook is the single chokepoint that turns one source tree
into two PyPI distributions. The brand is chosen by the ``MCP_BRAND`` environment
variable (``hydrolix`` -- the default -- or ``trafficpeak``); any other value
fails the build. For the TrafficPeak brand the hook rewrites the wheel's
distribution name, console-script, description, project URLs, author metadata,
and long-description (via a brand-substitution filter over ``README.md``), and
for *both* brands it bakes ``mcp_hydrolix/_brand.py`` into the wheel so the
runtime can report its identity from what was actually published rather than
from fragile signals like ``sys.argv[0]``.

Because the hook mutates metadata that is NOT visible by reading
``pyproject.toml``, the canonical way to inspect either wheel's real metadata is
to build it and unzip the METADATA file::

    MCP_BRAND=trafficpeak uv build
    unzip -p dist/*.whl '*/METADATA'

New build-time brand customization MUST go through this file (see
openspec design Decision: hatchling-hook) rather than through sibling
``pyproject.toml`` files or CI patch scripts.
"""

import os
import tempfile

# Hatchling is only present in the isolated build environment (it is the build
# backend), not in the project's own venv. Guard the import so the pure helper
# functions in this module (resolve_brand, brand_substitution_filter, ...) stay
# importable for unit tests; the hook class itself is only ever instantiated by
# Hatchling during an actual build, where these imports succeed.
try:
    from hatchling.builders.hooks.plugin.interface import BuildHookInterface
    from hatchling.plugin import hookimpl
except ModuleNotFoundError:  # pragma: no cover - exercised only outside a build
    BuildHookInterface = object  # type: ignore[assignment,misc]

    def hookimpl(func):  # type: ignore[misc]
        return func


#: Acceptable values of the ``MCP_BRAND`` build-time selector.
VALID_BRANDS = ("hydrolix", "trafficpeak")

#: Per-brand metadata table. ``hydrolix`` mirrors the static ``[project]`` block
#: (it is the default and must remain byte-for-byte today's wheel); only the
#: fields the hook actively rewrites for ``trafficpeak`` are listed.
BRANDS: dict[str, dict] = {
    "hydrolix": {
        "brand": "hydrolix",
        "dist_name": "mcp-hydrolix",
        "prose_name": "Hydrolix",
        "env_prefix": "HYDROLIX_",
        "description": "An MCP server for Hydrolix.",
        "urls": {"Home": "https://github.com/hydrolix/mcp-hydrolix"},
        "authors": None,
    },
    "trafficpeak": {
        "brand": "trafficpeak",
        "dist_name": "mcp-trafficpeak",
        "prose_name": "TrafficPeak",
        "env_prefix": "TRAFFICPEAK_",
        "description": "An MCP server for TrafficPeak.",
        # Source/account-level fields (repository, author) legitimately reference
        # the hydrolix org: mcp-trafficpeak is published under the same PyPI
        # account and its repository is github.com/hydrolix/mcp-trafficpeak. The
        # *customer-facing brand identity* (dist name, console script, runtime
        # output) stays TrafficPeak-only.
        "urls": {
            "Homepage": "https://www.akamai.com/products/akamai-trafficpeak",
            "Repository": "https://github.com/hydrolix/mcp-trafficpeak",
        },
        "authors": None,
    },
}


def resolve_brand() -> str:
    """Return the validated ``MCP_BRAND`` value (default ``hydrolix``).

    Raises ``ValueError`` -- which aborts the build before any wheel is produced
    -- for any value other than the two accepted brands.
    """
    brand = os.environ.get("MCP_BRAND", "hydrolix")
    if brand not in VALID_BRANDS:
        raise ValueError(
            f"Invalid MCP_BRAND={brand!r}: acceptable values are "
            f"{' or '.join(VALID_BRANDS)} (default: hydrolix)."
        )
    return brand


def brand_substitution_filter(text: str, brand: str) -> str:
    """Apply the per-brand substitution table to README/long-description text.

    Hydrolix mode is an identity transform. TrafficPeak mode rewrites the three
    brand-bearing token classes -- the distribution name (``mcp-hydrolix``), the
    env-var prefix (``HYDROLIX_``), and the prose brand name (``Hydrolix``).
    The lowercase import path ``mcp_hydrolix`` (underscore) is intentionally left
    untouched: both wheels import the same module.
    """
    if brand == "hydrolix":
        return text
    info = BRANDS[brand]
    text = text.replace("mcp-hydrolix", info["dist_name"])
    text = text.replace("HYDROLIX_", info["env_prefix"])
    text = text.replace("Hydrolix", info["prose_name"])
    return text


def render_brand_module(brand: str, dist_name: str) -> str:
    """Render the contents of the baked ``mcp_hydrolix/_brand.py`` module."""
    return (
        '"""Brand identity baked at build time by hatch_build.py. Do not edit."""\n'
        f'__brand__ = "{brand}"\n'
        f'__dist_name__ = "{dist_name}"\n'
    )


class BrandBuildHook(BuildHookInterface):
    """Rewrite wheel metadata and bake the runtime brand module per ``MCP_BRAND``."""

    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        brand = resolve_brand()
        info = BRANDS[brand]
        core = self.metadata.core
        cfg = core.config

        # 1. Bake mcp_hydrolix/_brand.py into the wheel for *both* brands. It is
        #    deliberately not committed to the source tree (so that a literal
        #    "mcp-hydrolix" never appears under mcp_hydrolix/); the runtime falls
        #    back to the Hydrolix brand when the module is absent (source runs).
        tmpdir = tempfile.mkdtemp(prefix="mcp_brand_")
        brand_py = os.path.join(tmpdir, "_brand.py")
        with open(brand_py, "w", encoding="utf-8") as f:
            f.write(render_brand_module(brand, info["dist_name"]))
        build_data.setdefault("force_include", {})[brand_py] = "mcp_hydrolix/_brand.py"

        # 2. Long-description: generated from this repo's README.md by the brand
        #    filter (identity for Hydrolix), so the TP PyPI landing page is
        #    single-sourced rather than vendored in the sibling repo.
        with open(os.path.join(self.root, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        cfg["readme"] = {
            "text": brand_substitution_filter(readme, brand),
            "content-type": "text/markdown",
        }
        core._readme = None
        core._readme_content_type = None
        core._readme_path = None

        # 3. Hydrolix is the default brand: leave all other static [project]
        #    metadata untouched so today's wheel is reproduced exactly.
        if brand == "hydrolix":
            return

        # 4. TrafficPeak: rewrite the brand-divergent metadata fields. Resetting
        #    the cached attributes forces Hatchling to re-derive them from the
        #    mutated config dict.
        cfg["name"] = info["dist_name"]
        cfg["description"] = info["description"]
        cfg["urls"] = info["urls"]
        cfg["scripts"] = {info["dist_name"]: "mcp_hydrolix.main:main"}
        if info["authors"]:
            cfg["authors"] = info["authors"]
        for attr in (
            "_raw_name",
            "_name",
            "_description",
            "_urls",
            "_scripts",
            "_authors",
            "_authors_data",
        ):
            setattr(core, attr, None)


@hookimpl
def hatch_register_build_hook():
    return BrandBuildHook
