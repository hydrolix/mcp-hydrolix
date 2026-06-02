#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to the repo root regardless of the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# 0. Select the brand. MCP_BRAND mirrors the Hatchling build hook (default
#    hydrolix). The per-brand vars table below is the single source of every
#    brand-divergent value substituted into the manifest + bundle pyproject.
# ---------------------------------------------------------------------------
MCP_BRAND="${MCP_BRAND:-hydrolix}"
case "${MCP_BRAND}" in
  hydrolix)
    DIST_NAME="mcp-hydrolix"
    DISPLAY_NAME="Hydrolix"
    DESCRIPTION="An MCP server for the Hydrolix analytics database."
    LONG_DESCRIPTION="Query Hydrolix from Claude using SQL. Provides tools to list databases and tables, inspect schemas, and run SELECT queries."
    AUTHOR_NAME="Hydrolix"
    AUTHOR_URL="https://hydrolix.io"
    HOMEPAGE="https://github.com/hydrolix/mcp-hydrolix"
    REPOSITORY="https://github.com/hydrolix/mcp-hydrolix"
    KEYWORDS='["hydrolix", "sql", "clickhouse", "analytics", "observability", "logs"]'
    ENV_PREFIX="HYDROLIX_"
    CFG_PREFIX="hydrolix"
    EXAMPLE_URL="https://mycluster.hydrolix.live"
    ;;
  trafficpeak)
    DIST_NAME="mcp-trafficpeak"
    DISPLAY_NAME="TrafficPeak"
    DESCRIPTION="An MCP server for the TrafficPeak analytics database."
    LONG_DESCRIPTION="Query TrafficPeak from Claude using SQL. Provides tools to list databases and tables, inspect schemas, and run SELECT queries."
    # Source/account-level fields legitimately reference the hydrolix org (the
    # bundle is published under the same account; repo is hydrolix/mcp-trafficpeak).
    # The customer-facing brand identity below (display_name, user_config titles,
    # env keys, dist name) stays TrafficPeak-only.
    AUTHOR_NAME="Hydrolix"
    AUTHOR_URL="https://hydrolix.io"
    HOMEPAGE="https://www.akamai.com/products/akamai-trafficpeak"
    REPOSITORY="https://github.com/hydrolix/mcp-trafficpeak"
    KEYWORDS='["trafficpeak", "sql", "clickhouse", "analytics", "observability", "logs"]'
    ENV_PREFIX="TRAFFICPEAK_"
    CFG_PREFIX="trafficpeak"
    EXAMPLE_URL="https://mycluster.trafficpeak.live"
    ;;
  *)
    echo "ERROR: invalid MCP_BRAND='${MCP_BRAND}' (expected 'hydrolix' or 'trafficpeak')" >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# 1. Determine the version. MCPB_VERSION overrides; otherwise read from
#    pyproject.toml using stdlib tomllib (Python 3.11+). The override is
#    useful for testing the bundle against an already-published PyPI
#    release that differs from the in-development version.
# ---------------------------------------------------------------------------
if [[ -n "${MCPB_VERSION:-}" ]]; then
  VERSION="${MCPB_VERSION}"
else
  VERSION="$(uv run --quiet python -c \
    'import tomllib; f=open("pyproject.toml","rb"); print(tomllib.load(f)["project"]["version"])')"
fi

if [[ -z "${VERSION}" ]]; then
  echo "ERROR: could not determine version (MCPB_VERSION unset, pyproject.toml unreadable)" >&2
  exit 1
fi

echo "Building ${DIST_NAME} version ${VERSION} ..."

# ---------------------------------------------------------------------------
# 2. Expand templates. Use | as sed delimiter so / in URLs and PEP 440 local
#    segments does not corrupt the substitution. \${PLACEHOLDER} in the pattern
#    prevents the shell from expanding it before sed sees it; the right-hand
#    side IS expanded by the shell intentionally. The mcpb runtime placeholders
#    ${__dirname} and ${user_config.*} are deliberately left untouched.
#    CFG_PREFIX is substituted inside the nested ${user_config.${CFG_PREFIX}_*}
#    tokens, yielding e.g. ${user_config.trafficpeak_url}.
# ---------------------------------------------------------------------------
expand() {
  sed \
    -e "s|\${VERSION}|${VERSION}|g" \
    -e "s|\${DIST_NAME}|${DIST_NAME}|g" \
    -e "s|\${DISPLAY_NAME}|${DISPLAY_NAME}|g" \
    -e "s|\${DESCRIPTION}|${DESCRIPTION}|g" \
    -e "s|\${LONG_DESCRIPTION}|${LONG_DESCRIPTION}|g" \
    -e "s|\${AUTHOR_NAME}|${AUTHOR_NAME}|g" \
    -e "s|\${AUTHOR_URL}|${AUTHOR_URL}|g" \
    -e "s|\${HOMEPAGE}|${HOMEPAGE}|g" \
    -e "s|\${REPOSITORY}|${REPOSITORY}|g" \
    -e "s|\${KEYWORDS}|${KEYWORDS}|g" \
    -e "s|\${EXAMPLE_URL}|${EXAMPLE_URL}|g" \
    -e "s|\${ENV_PREFIX}|${ENV_PREFIX}|g" \
    -e "s|\${CFG_PREFIX}|${CFG_PREFIX}|g" \
    "$1"
}

expand mcpb/manifest.json.tmpl > mcpb/manifest.json
expand mcpb/pyproject.toml.tmpl > mcpb/pyproject.toml

# ---------------------------------------------------------------------------
# 3. Copy icon into the bundle source directory.
# ---------------------------------------------------------------------------
cp icon.png mcpb/icon.png

# ---------------------------------------------------------------------------
# 4. Validate and pack via the MCPB CLI. `npx --yes` fetches the latest
#    @anthropic-ai/mcpb on every run, which keeps the script simple but
#    makes builds non-reproducible across CLI releases. Pin via
#    `@anthropic-ai/mcpb@<version>` when reproducibility matters (e.g. CI).
# ---------------------------------------------------------------------------
npx --yes @anthropic-ai/mcpb validate mcpb/manifest.json

# ---------------------------------------------------------------------------
# 5. Pack the bundle. Filename convention: dist/mcp-<brand>-<version>.mcpb so
#    both brands' bundles coexist in dist/ without collision.
# ---------------------------------------------------------------------------
mkdir -p dist
ARTIFACT="dist/${DIST_NAME}-${VERSION}.mcpb"
npx --yes @anthropic-ai/mcpb pack mcpb "${ARTIFACT}"

echo "Built: ${ARTIFACT}"
