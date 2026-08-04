"""Build-time-baked brand identity for the MCP server.

This module is the SINGLE runtime source of truth for the server's brand,
distribution name, and env-var namespace behavior. No other code path may infer
these from any other signal (``sys.argv[0]``, the env-var namespace that
supplied credentials, etc.).

The committed contents below are the Hydrolix defaults -- what a source-tree /
editable install (dev, tests, ``uv build`` with no ``MCP_BRAND``) sees. At
wheel-build time the custom Hatchling hook in ``hatch_build.py`` overwrites this
file from ``brands.toml`` so the baked values match the brand being built. Do
NOT edit the values by hand to diverge from ``brands.toml`` -- that file is the
build-time single source of truth; these are its baked projection.

Constants:
  __brand__                  short brand id ("hydrolix" | "trafficpeak")
  __dist_name__              PyPI distribution name ("mcp-hydrolix" | ...)
  __env_prefix__             this brand's OWN env-var prefix (for error hints)
  __env_prefix_precedence__  dual-namespace read precedence (first wins)

Inspect what a built wheel baked::

    unzip -p dist/*.whl 'mcp_hydrolix/_brand.py'
"""

__brand__ = "hydrolix"
__dist_name__ = "mcp-hydrolix"
__env_prefix__ = "HYDROLIX_"
__env_prefix_precedence__ = ("TRAFFICPEAK_", "HYDROLIX_")
