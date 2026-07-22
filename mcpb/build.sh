#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to the repo root regardless of the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# 0. Select the brand. MCP_BRAND={hydrolix|trafficpeak} (default hydrolix),
#    mirroring the Hatchling build hook. The per-brand table below is the
#    single source of brand-divergent mcpb metadata.
# ---------------------------------------------------------------------------
MCP_BRAND="${MCP_BRAND:-hydrolix}"
case "${MCP_BRAND}" in
  hydrolix)
    DIST_NAME="mcp-hydrolix"
    DISPLAY_NAME="Hydrolix"
    BRAND_NAME="Hydrolix"
    DESCRIPTION="An MCP server for the Hydrolix analytics database."
    LONG_DESCRIPTION="Query Hydrolix from Claude using SQL. Provides tools to list databases and tables, inspect schemas, and run SELECT queries."
    AUTHOR_NAME="Hydrolix"
    AUTHOR_URL="https://hydrolix.io"
    HOMEPAGE="https://github.com/hydrolix/mcp-hydrolix"
    REPOSITORY="https://github.com/hydrolix/mcp-hydrolix"
    KEYWORDS='["hydrolix", "sql", "clickhouse", "analytics", "observability", "logs"]'
    ENV_PREFIX="HYDROLIX_"
    CFG_PREFIX="hydrolix_"
    EXAMPLE_URL="https://mycluster.hydrolix.live"
    ;;
  trafficpeak)
    DIST_NAME="mcp-trafficpeak"
    DISPLAY_NAME="TrafficPeak"
    BRAND_NAME="TrafficPeak"
    DESCRIPTION="An MCP server for the TrafficPeak analytics database."
    LONG_DESCRIPTION="Query TrafficPeak from Claude using SQL. Provides tools to list databases and tables, inspect schemas, and run SELECT queries."
    AUTHOR_NAME="TrafficPeak"
    AUTHOR_URL="https://www.akamai.com/products/trafficpeak"
    HOMEPAGE="https://www.akamai.com/products/trafficpeak"
    # The repository field points at the real sibling repo under the hydrolix
    # org -- an accepted exemption to the zero-hydrolix rule for repo pointers.
    REPOSITORY="https://github.com/hydrolix/mcp-trafficpeak"
    KEYWORDS='["trafficpeak", "sql", "clickhouse", "analytics", "observability", "logs"]'
    ENV_PREFIX="TRAFFICPEAK_"
    CFG_PREFIX="trafficpeak_"
    EXAMPLE_URL="https://mycluster.trafficpeak.live"
    ;;
  *)
    echo "ERROR: MCP_BRAND='${MCP_BRAND}' is not valid. Use 'hydrolix' or 'trafficpeak'." >&2
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
#    segments does not corrupt the substitution. Each \${PLACEHOLDER} in the
#    pattern is escaped so the shell does not expand it before sed sees it; the
#    right-hand side IS expanded by the shell intentionally. The mcpb runtime
#    variables ${user_config.*} and ${__dirname} are deliberately NOT in this
#    list, so they survive untouched for the mcpb host to resolve at install.
# ---------------------------------------------------------------------------
render() {
  sed \
    -e "s|\${VERSION}|${VERSION}|g" \
    -e "s|\${DIST_NAME}|${DIST_NAME}|g" \
    -e "s|\${DISPLAY_NAME}|${DISPLAY_NAME}|g" \
    -e "s|\${BRAND_NAME}|${BRAND_NAME}|g" \
    -e "s|\${DESCRIPTION}|${DESCRIPTION}|g" \
    -e "s|\${LONG_DESCRIPTION}|${LONG_DESCRIPTION}|g" \
    -e "s|\${AUTHOR_NAME}|${AUTHOR_NAME}|g" \
    -e "s|\${AUTHOR_URL}|${AUTHOR_URL}|g" \
    -e "s|\${HOMEPAGE}|${HOMEPAGE}|g" \
    -e "s|\${REPOSITORY}|${REPOSITORY}|g" \
    -e "s|\${KEYWORDS}|${KEYWORDS}|g" \
    -e "s|\${ENV_PREFIX}|${ENV_PREFIX}|g" \
    -e "s|\${CFG_PREFIX}|${CFG_PREFIX}|g" \
    -e "s|\${EXAMPLE_URL}|${EXAMPLE_URL}|g" \
    "$1"
}

render mcpb/manifest.json.tmpl > mcpb/manifest.json
render mcpb/pyproject.toml.tmpl > mcpb/pyproject.toml

# Render-only mode: stop after template expansion, before the network-fetching
# `npx @anthropic-ai/mcpb validate/pack` steps. Used by tests (and CI dry-runs)
# to assert the rendered manifest is brand-correct without packing a bundle.
if [[ -n "${MCPB_RENDER_ONLY:-}" ]]; then
  echo "Rendered mcpb/manifest.json for ${DIST_NAME} (MCPB_RENDER_ONLY set); skipping validate/pack."
  exit 0
fi

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
# 5. Pack the bundle. Output name carries the brand so both brands' bundles
#    coexist in dist/ at the same version without collision.
# ---------------------------------------------------------------------------
mkdir -p dist
ARTIFACT="dist/${DIST_NAME}-${VERSION}.mcpb"
npx --yes @anthropic-ai/mcpb pack mcpb "${ARTIFACT}"

echo "Built: ${ARTIFACT}"
