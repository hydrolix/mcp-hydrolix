#!/usr/bin/env bash
# Build and push the local working tree as an image suitable for the e2e suite.
# Prints two `export` lines on success so callers can re-use the result with
# MCP_HYDROLIX_E2E_SKIP_BUILD=1.
#
# Mirrors the same derivation logic as tests/e2e/conftest.py so manual and
# automated paths stay in lockstep.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

branch="${MCP_HYDROLIX_E2E_BRANCH:-$(git rev-parse --abbrev-ref HEAD)}"
short_sha="$(git rev-parse --short=7 HEAD)"
sanitized_branch="$(echo "$branch" | sed 's/[^a-zA-Z0-9._-]/-/g')"

dirty=""
if ! git diff --quiet HEAD; then
  dirty="-dirty"
fi

image="${MCP_HYDROLIX_E2E_IMAGE:-}"
if [[ -z "$image" ]]; then
  user="${USER:-$(id -un)}"
  image="ttl.sh/mcp-hydrolix-e2e-${user}-${sanitized_branch}-${short_sha}${dirty}"
  default_tag="1h"
else
  default_tag="branch-${sanitized_branch}-${short_sha}${dirty}"
fi
tag="${MCP_HYDROLIX_E2E_IMAGE_TAG:-$default_tag}"

echo "Building $image:$tag" >&2
docker build -t "$image:$tag" .
echo "Pushing $image:$tag" >&2
docker push "$image:$tag"

cat <<EOF
export MCP_HYDROLIX_E2E_IMAGE='$image'
export MCP_HYDROLIX_E2E_IMAGE_TAG='$tag'
export MCP_HYDROLIX_E2E_SKIP_BUILD=1
EOF
