*Ship a `mcp-trafficpeak` PyPI distribution alongside `mcp-hydrolix` — one source tree, every release artifact paired, no Hydrolix branding on TP customer surfaces.*

## Why

TrafficPeak launches must be self-contained — no Hydrolix branding visible to end users (HDX-11476). Today's `mcp-hydrolix` PyPI distribution forces TP customers to paste Hydrolix-branded identifiers into their AI tool config (`mcp-hydrolix` console-script, `HYDROLIX_*` env vars), which leaks the underlying brand into every TP onboarding.

## What Changes

- Add a TP-branded PyPI distribution `mcp-trafficpeak` built from the same source as `mcp-hydrolix` at the same version, published from a minimal sibling repo that checks out this repo at the release tag.
- Source every customer-visible MCP-server identifier (startup log, outbound `User-Agent`, FastMCP server name, query admin-comment User token) from a build-time-baked constant, not from runtime signals.
- Accept a parallel `TRAFFICPEAK_*` runtime env-var namespace mirroring the full `HYDROLIX_*` namespace; resolve as full-chain TP-then-Hydrolix, never per-variable interleaved.
- Enforce an **artifact-parity invariant**: every Hydrolix release artifact MUST have a same-version TrafficPeak counterpart produced in the same workflow run.
- Brand-parameterize the mcpb bundle.
- Customer-facing docs in this repo stay Hydrolix-only; the TP PyPI landing page is generated from this repo's `README.md` at build time via a brand-substitution filter.
- **No breaking change** — existing `mcp-hydrolix` distribution, console-script, `HYDROLIX_*` env vars, and `mcp_hydrolix` Python import path are preserved.

## Capabilities

### New

- `mcp-server-branding` — how the MCP server's distribution name, console-script, runtime identifier, env-var contract, and release artifacts are determined per brand

### Modified

*none*

## Impact

- `pyproject.toml` and a new sibling build-hook file.
- `mcp_hydrolix/` — gains a small brand-identifier module written at build time and consumed at runtime (notably by the `MCP_SERVER_NAME` constant).
- Config-loading layer — wrapped to run the resolver over `TRAFFICPEAK_*` first, then fall back to `HYDROLIX_*`.
- `.github/workflows/publish.yml` — every artifact-producing job gains a paired TP build/upload step.
- `mcpb/build.sh`, `mcpb/manifest.json.tmpl`, `mcpb/pyproject.toml.tmpl` — brand-parameterized.
- New sibling repository `hydrolix/mcp-trafficpeak` — publish workflow, GitHub-visitor `README.md`, and issue-triage template; no source, no tests, no vendored customer-facing readme.
- External: `mcp-trafficpeak` PyPI Trusted Publisher and GAR repo provisioning (release-blocking ops prereqs).
- No data migration. No change to the `mcp_hydrolix` Python import path or `HYDROLIX_*` env-var contract.
