#!/usr/bin/env bash
# Benchmark the effect of image-baked bytecode on container startup time.
#
# Builds two images from the same build context:
#   baseline  - Dockerfile taken from a baseline git ref (default: main)
#   candidate - Dockerfile from the working tree
# then, for each, spins up N fresh containers and measures the wall-clock
# time to import the server's module tree (mcp_hydrolix.main +
# mcp_hydrolix.mcp_server, which pulls in fastmcp/clickhouse_connect/sqlglot).
# That import is the bytecode-sensitive portion of startup: without baked
# .pyc files every container start re-parses and re-compiles the whole
# dependency tree; with them, Python loads cached bytecode.
#
# Timing happens inside the container (time.perf_counter around the imports),
# so docker's own container-launch overhead is excluded from the numbers.
#
# Usage: scripts/benchmark_docker_startup.sh [-n iterations] [-r baseline-ref]
set -euo pipefail

ITERATIONS=10
BASELINE_REF=main
while getopts "n:r:" opt; do
  case "$opt" in
    n) ITERATIONS="$OPTARG" ;;
    r) BASELINE_REF="$OPTARG" ;;
    *) echo "usage: $0 [-n iterations] [-r baseline-ref]" >&2; exit 2 ;;
  esac
done

cd "$(dirname "$0")/.."

BASELINE_IMG=mcp-hydrolix:bench-baseline
CANDIDATE_IMG=mcp-hydrolix:bench-candidate

echo "Building baseline image (Dockerfile @ ${BASELINE_REF})..." >&2
git show "${BASELINE_REF}:Dockerfile" | docker build -q -f - -t "$BASELINE_IMG" . >&2

echo "Building candidate image (working-tree Dockerfile)..." >&2
docker build -q -t "$CANDIDATE_IMG" . >&2

# Sanity check: the candidate image must actually contain baked bytecode.
docker run --rm --entrypoint sh "$CANDIDATE_IMG" -c \
  'test -n "$(ls /app/mcp_hydrolix/__pycache__/*.pyc 2>/dev/null)"' ||
  { echo "ERROR: candidate image has no baked bytecode in /app/mcp_hydrolix/__pycache__" >&2; exit 1; }

IMPORT_TIMER='import time; t = time.perf_counter(); import mcp_hydrolix.main, mcp_hydrolix.mcp_server; print(f"{time.perf_counter() - t:.4f}")'

bench() {
  local img="$1" label="$2"
  local samples=()
  for _ in $(seq "$ITERATIONS"); do
    # Dummy HYDROLIX_URL: config validation runs at import time and requires a
    # cluster URL for the http transport; no connection is made during import.
    samples+=("$(docker run --rm -e HYDROLIX_URL=https://bench.invalid \
      --entrypoint .venv/bin/python "$img" -c "$IMPORT_TIMER")")
  done
  printf '%s\n' "${samples[@]}" | python3 -c '
import statistics, sys
label = sys.argv[1]
xs = [float(line) for line in sys.stdin if line.strip()]
print(f"{label:>32}: mean {statistics.mean(xs):.3f}s  median {statistics.median(xs):.3f}s  "
      f"min {min(xs):.3f}s  max {max(xs):.3f}s  (n={len(xs)})")
' "$label"
}

echo "Running ${ITERATIONS} iterations per image..." >&2
bench "$BASELINE_IMG" "baseline (no baked bytecode)"
bench "$CANDIDATE_IMG" "candidate (baked bytecode)"
