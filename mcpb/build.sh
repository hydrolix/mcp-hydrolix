#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to the repo root regardless of the caller's cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

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

echo "Building mcp-hydrolix version ${VERSION} ..."

# ---------------------------------------------------------------------------
# 2. Expand templates. Use | as sed delimiter so / in PEP 440 local segments
#    does not corrupt the substitution. \${VERSION} in the pattern prevents
#    the shell from expanding the placeholder before sed sees it; ${VERSION}
#    on the right-hand side IS expanded by the shell intentionally.
# ---------------------------------------------------------------------------
sed -e "s|\${VERSION}|${VERSION}|g" mcpb/manifest.json.tmpl > mcpb/manifest.json
sed -e "s|\${VERSION}|${VERSION}|g" mcpb/pyproject.toml.tmpl > mcpb/pyproject.toml

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
# 5. Pack the bundle.
# ---------------------------------------------------------------------------
mkdir -p dist
ARTIFACT="dist/mcp-hydrolix-${VERSION}.mcpb"
npx --yes @anthropic-ai/mcpb pack mcpb "${ARTIFACT}"

echo "Built: ${ARTIFACT}"
