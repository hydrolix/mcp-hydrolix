"""Runtime brand identity (mcp-hydrolix / mcp-trafficpeak).

The build-time Hatchling hook (``hatch_build.py``) bakes ``mcp_hydrolix/_brand.py``
into every wheel with the published ``__brand__`` and ``__dist_name__``. This
module reads those baked constants and exposes them, plus the server version and
outbound ``User-Agent`` token, to the rest of the package.

The baked constants are the most honest brand signal -- a launcher can rewrite
the process argv, and the env-var prefix can be misconfigured, but the wheel is
what we actually published.

When running from the source tree (no wheel build, e.g. tests or ``uv run``),
``_brand.py`` is absent and we fall back to the Hydrolix brand. The distribution
name is derived (``f"mcp-{BRAND}"``) rather than written as a literal so that the
quoted distribution-name literal never appears anywhere in the source package.
"""

import logging
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    from mcp_hydrolix._brand import __brand__ as BRAND, __dist_name__ as DIST_NAME
except ImportError:  # running from source; no build-time-baked brand module
    BRAND = "hydrolix"
    DIST_NAME = f"mcp-{BRAND}"

logger = logging.getLogger(DIST_NAME)


def _resolve_version() -> str:
    """Return the installed distribution version, or ``"unknown"`` from source."""
    try:
        return _pkg_version(DIST_NAME)
    except PackageNotFoundError:
        logger.warning(
            "Could not resolve package version for %s; using 'unknown' in admin comment",
            DIST_NAME,
        )
        return "unknown"


#: Version of the installed brand distribution (``"unknown"`` when run from source).
SERVER_VERSION: str = _resolve_version()

#: Leading token of the outbound HTTP ``User-Agent`` on calls to the cluster API.
USER_AGENT: str = f"{DIST_NAME}/{SERVER_VERSION}"
