"""Build-time-baked brand identity for the MCP server.

This module is the SINGLE source of truth for the server's brand and
distribution name at runtime. No other code path may infer the brand or
distribution name from any other signal (``sys.argv[0]``, the env-var namespace
that supplied credentials, etc.).

The committed contents below are the Hydrolix defaults, which is what a
source-tree / editable install (dev, tests, ``uv build`` with no ``MCP_BRAND``)
sees. At wheel-build time the custom Hatchling hook in ``hatch_build.py``
overwrites this file inside the build directory so the value baked into the
wheel matches the brand being built (``MCP_BRAND=trafficpeak`` bakes the
TrafficPeak identity). See ``hatch_build.py`` for the per-brand table.

To inspect what a built wheel actually baked::

    unzip -p dist/*.whl 'mcp_hydrolix/_brand.py'
"""

__brand__ = "hydrolix"
__dist_name__ = "mcp-hydrolix"
