#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to the repo root regardless of the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# ---------------------------------------------------------------------------
# 0. Select the brand and load its values from brands.toml (the single source
#    of truth). scripts/brand_meta.py validates MCP_BRAND (defaulting from
#    brands.toml when unset) and emits the shell vars used below; `set -e`
#    aborts the build if the brand is invalid. No per-brand table lives here.
# ---------------------------------------------------------------------------
brand_vars="$(uv run --quiet python scripts/brand_meta.py "${MCP_BRAND:-}")"
eval "${brand_vars}"

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
