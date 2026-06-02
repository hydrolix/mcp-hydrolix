*One source tree, one `pyproject.toml`, one Hatchling hook flipping `MCP_BRAND` — every release artifact paired, never interleaved at runtime.*

## Context

- This repo *is* the source of the published `mcp-hydrolix` PyPI distribution; `pyproject.toml` declares `hatchling.build` as the backend and a single console-script `mcp-hydrolix = "mcp_hydrolix.main:main"`.
- Per-release artifact surface (all produced from `.github/workflows/publish.yml` on a `v*` tag):
    - PyPI wheel + sdist
    - mcpb bundle
    - Docker image
- The mcpb manifest template (`mcpb/manifest.json.tmpl`) currently hard-codes `name: mcp-hydrolix`, Hydrolix author/homepage/repo, `HYDROLIX_*` env-var keys in `server.mcp_config.env`, and `hydrolix_*` `user_config` field keys.
- Sibling change `hydrolix-url-config-collapse` introduces a four-tier precedence resolver (`explicit new var > deprecated alias > URL-derived > hard default`) over the `HYDROLIX_*` namespace; this change wraps that resolver to also operate over `TRAFFICPEAK_*`, which exposes only the modern (non-deprecated) variables — the deprecated-alias tier applies to `HYDROLIX_*` only.

## Goals / Non-Goals

**Goals:**

- TP customers paste a snippet with only TP-branded identifiers (`mcp-trafficpeak`, `TRAFFICPEAK_*`) and get a working MCP server.
- One source tree, no version skew, no forked code; both brands ship from the same release commit at the same version.
- Local `MCP_BRAND=trafficpeak uv build` reproduces the CI TP wheel exactly.
- Runtime brand identifier reflects what was *published in the wheel*, not fragile signals like `sys.argv[0]`.
- Hydrolix-branded customer surfaces stay clean of TP references; TP-branded customer surfaces stay clean of Hydrolix references.

**Non-Goals:**

- Renaming the Python import path `mcp_hydrolix`. Both wheels import the same module.
- Removing Hydrolix branding from `mcp-hydrolix`. Both brands coexist.

## Decisions

### Decision: hatchling-hook

- **Choice:** A `BuildHookInterface` subclass in `hatch_build.py` reads `MCP_BRAND={hydrolix|trafficpeak}` (default `hydrolix`) and mutates `project.name`, `[project.scripts]`, `project.urls`, author/maintainer/description, and bakes `__brand__` into `mcp_hydrolix/_brand.py` inside the wheel. The hook also reads this repo's `README.md`, applies a brand-substitution filter to its contents (literal token substitutions per `MCP_BRAND`: `mcp-hydrolix` → `mcp-trafficpeak`, `HYDROLIX_` → `TRAFFICPEAK_`, prose-level brand-name occurrences as configured in a per-brand substitution table), and uses the result as the wheel's `long_description`. In Hydrolix mode the filter is an identity transform. This way the `mcp-trafficpeak` PyPI landing page is generated from this repo's single-source `README.md` at publish time rather than being maintained as a vendored file in the sibling repo (see Decision: tp-pypi-via-sibling-repo).
- **Why:** Implements `explore/approach-hatchling-hook`. Sibling `pyproject.toml` files drift on every shared-field add; CI-only rewrite scripts break local repro; shim packages re-leak Hydrolix via transitive deps in lockfiles. The Hatchling hook is the only option that's single-source, locally reproducible, and confined to one discoverable file.
- **Alternatives:** Sibling `pyproject.toml` (uv workspace) — rejected, hand-mirror surface grows unbounded. CI-only `tomlkit` rewrite — rejected, local `uv build` only ever produces Hydrolix wheel. Thin shim package `mcp-trafficpeak` depending on `mcp-hydrolix` — rejected, transitive dep leaks Hydrolix into `uv tree` / lockfiles. `uv_build` backend — rejected, intentionally disallows dynamic `project.name`.
- **Binding:** `hatch_build.py` MUST be the sole source of brand-divergent metadata; new build-time customization MUST go through this hook rather than through sibling configs or CI patches.

### Decision: dual-namespace-precedence

- **Choice:** At startup, run the full `hydrolix-url-config-collapse` resolver once over the entire `TRAFFICPEAK_*` namespace; if it yields a layer-1 anchor (`TRAFFICPEAK_URL` — the only TP anchor, since `TRAFFICPEAK_*` mirrors only the modern variable scheme and not the deprecated aliases) use that result and ignore `HYDROLIX_*` entirely. Otherwise re-run the same resolver over `HYDROLIX_*` (anchored by `HYDROLIX_URL`, or the deprecated `HYDROLIX_HOST` for stdio). Both chains resolving to different effective configs → prefer TP, emit one WARNING log line. Identical → silent. Neither → exit non-zero naming `TRAFFICPEAK_URL` and `HYDROLIX_URL`.
- **Why:** Implements `explore/env-var-namespace-chain`. Per-variable interleaving is pathological — a TP customer with `TRAFFICPEAK_URL` set but an inherited `HYDROLIX_HTTP_QUERY_HOST` would silently get a half-TP / half-Hydrolix config pointing at two clusters. Whole-chain semantics preserve the resolver's invariants and let the existing implementation be reused under a thin namespace-parameter wrapper.
- **Alternatives:** Per-variable interleaved precedence — rejected, see above. Separate `--brand` / `MCP_MODE` flag to pick the namespace — rejected, the namespace itself is sufficient signal.
- **Binding:** The resolver implementation MUST take the env-var prefix as a parameter and MUST NOT be duplicated; callers MUST run the TP resolution and the Hydrolix resolution as two whole-chain invocations, not interleave them.

### Decision: brand-identifier-baked

- **Choice:** The hatchling hook bakes a small `mcp_hydrolix/_brand.py` module containing `__brand__` (short identifier, `"hydrolix"` or `"trafficpeak"`) and `__dist_name__` (the matching PyPI distribution name, `"mcp-hydrolix"` or `"mcp-trafficpeak"`). Runtime code sources both from this module — no other code path may infer brand or distribution name from any signal. Every customer-visible identifier that today uses the literal `"mcp-hydrolix"` MUST source from `__dist_name__` instead:
    - the startup log line
    - the leading token of outbound `User-Agent` on calls to the configured cluster
    - the `name=` argument passed to the FastMCP server constructor (the `MCP_SERVER_NAME` constant)
    - the `User` token in the `hdx_query_admin_comment` setting attached to outbound SQL queries

- **Why:** The wheel identity is the most honest signal of intended brand — argv can be rewritten by launchers, env-var prefix can be misconfigured. The baked constants are what we actually published.
- **Alternatives:** `sys.argv[0]` sniffing — rejected, fragile under launchers / IDE wrappers. Derive from env-var prefix matched — rejected, env vars can be misconfigured independently of intended brand. Derive `__dist_name__` from `__brand__` via `f"mcp-{__brand__}"` at runtime — rejected, baking both removes runtime string-templating and keeps the brand→dist-name mapping in one declarative place (the hook's per-brand table).
- **Binding:** No code path may infer brand or distribution name from any signal other than `_brand.py`. The literal string `"mcp-hydrolix"` MUST NOT appear in customer-visible runtime output paths (log lines, outbound HTTP headers, query-side comment fields, MCP-protocol server-name advertisement). Tests MUST assert this by patching env / argv and confirming reported brand and dist name are unchanged.

### Decision: docs-hydrolix-only

- **Choice:** `README.md` and any other customer-facing doc files in this repo reference only `mcp-hydrolix` / `HYDROLIX_*`. TP-branded snippets live in TP customer documentation maintained outside this repository.
- **Why:** Implements `explore/docs-hydrolix-only-in-repo`. This `README.md` is published verbatim to PyPI as the `mcp-hydrolix` landing page. Surfacing TP branding there would leak the dual-brand reality into the Hydrolix-customer surface — the inverse of the leak HDX-11476 is fixing.
- **Alternatives:** Side-by-side TP + Hydrolix snippets in README — rejected, leaks TP into PyPI landing. Rendered-variant docs (one source, conditional include) — rejected, premature complexity for a single doc.
- **Binding:** A repo-grep for the literal string `trafficpeak` (case-insensitive) against `README.md` and any top-level customer-facing doc files MUST return zero matches. Internal engineering docs (this OpenSpec change, source comments, CONTRIBUTING) are exempt.

### Decision: tp-pypi-via-sibling-repo

- **Choice:** Publish `mcp-trafficpeak` to PyPI from a minimal sibling repo `hydrolix/mcp-trafficpeak`. The sibling contains a single publish workflow that listens for `workflow_dispatch` events fired from this repo's `publish.yml`, checks out `hydrolix/mcp-hydrolix@<tag>` (passed as a typed input), runs `MCP_BRAND=trafficpeak uv build`, and publishes via its own Trusted Publisher config (which PyPI accepts because the project name matches the repo name). The customer-facing `mcp-trafficpeak` PyPI landing page is generated at build time by the hatchling hook's brand-substitution filter applied to this repo's `README.md` (see Decision: hatchling-hook); the sibling does NOT vendor a `PYPI_README.md`. The sibling additionally owns:
    - a short `README.md` for GitHub visitors (explains why the repo exists and how the dispatch flow works; does NOT contain customer install instructions)
    - an issue-triage template

    It owns none of:
    - Python source
    - tests
    - mcpb templates
    - Docker configuration
    - any vendored customer-facing readme
- **Why:** Implements `explore/tp-pypi-via-sibling-repo`. PyPI rejects a Trusted Publisher request to publish `mcp-trafficpeak` from `hydrolix/mcp-hydrolix` with "Invalid repository name", and uvx is the canonical TP-customer install path so dropping PyPI is not an option. The sibling-repo workaround preserves the single-source guarantee (the sibling has no source to drift from) and confines the workaround to whatever PyPI's identity binds against — the publish workflow plus the README PyPI renders. Other artifacts (mcpb, Docker) have no analogous identity coupling and stay in this repo.
- **Alternatives:** Drop PyPI publication for TP (use mcpb/Docker only) — rejected, uvx is the canonical install path. Use an API token instead of Trusted Publisher for the TP wheel — rejected, conflicts with Hydrolix policy on TP. Sibling repo polls this repo's release tags — rejected, adds latency and a separate failure mode vs. synchronous dispatch. Use `repository_dispatch` instead of `workflow_dispatch` — rejected, `workflow_dispatch` targets a named workflow with typed inputs and is also fireable from `gh workflow run` for disaster recovery. Vendor source into the sibling repo — rejected, that *is* the version-skew failure mode the design exists to prevent.
- **Binding:** The sibling repo MUST NOT contain:
    - Python source
    - tests
    - `pyproject.toml`
    - mcpb templates
    - Docker configuration

    It MAY (and SHOULD) contain configuration files required by any external surface that binds the `mcp-trafficpeak` *name* — registry manifests, marketplace listings, identity tokens for future registrations — added on the same reasoning that places the PyPI Trusted Publisher binding here. The test for whether something belongs in the sibling is: "does the external surface bind to the name `mcp-trafficpeak` (sibling) or to the source repo for arbitrary reasons unrelated to brand (this repo)?" If a future change would place Python source, tests, mcpb templates, or Docker configuration in the sibling, the cut has drifted from "publishing identity" and should be reconsidered. The dispatch mechanism MUST be `workflow_dispatch` (not `repository_dispatch`) targeting the sibling's named publish workflow with the release tag as a typed `string` input.

### Decision: artifact-parity

- **Choice:** Pair every release artifact at version V. `publish-docker` (GAR) and `publish-mcpb` each run their build+publish step twice in the same job — once with `MCP_BRAND=hydrolix`, once with `MCP_BRAND=trafficpeak` — and a post-build assertion checks both outputs exist before any upload completes. The `publish` (PyPI) job publishes only `mcp-hydrolix` from this repo and then fires `workflow_dispatch` to `hydrolix/mcp-trafficpeak`'s publish workflow carrying the release tag; the sibling repo's workflow publishes `mcp-trafficpeak` at the same version V from the same source commit (per Decision: tp-pypi-via-sibling-repo). The dispatch step in this repo MUST succeed for the release to be considered started; the sibling's actual publish completion is verified post-release in the rollout phase (it is asynchronous from this repo's workflow).
- **Why:** Implements `explore/artifact-parity-invariant`. Version skew between the two brands is the failure mode the dual distribution exists to prevent. CI structure enforces parity; a post-build pairing assertion catches new artifact types added by future PRs.
- **Alternatives:** TP artifacts on a separate release cadence — rejected, reintroduces version skew. Thin TP wrapper repo that pulls and republishes — rejected, doubles the release pipeline and re-leaks Hydrolix via transitive deps.
- **Binding:** Any future PR adding a release-time artifact MUST add both Hydrolix and TP outputs in the same job, and MUST extend the pairing assertion. The release workflow MUST fail before any partial-brand upload completes.

### Decision: mcpb-template-parameterized

- **Choice:** `mcpb/build.sh` reads `MCP_BRAND` (default `hydrolix`) and substitutes brand-specific values from a per-brand vars table into `manifest.json.tmpl` and `pyproject.toml.tmpl` (covering distribution name, display name, author/homepage/repo, user-config keys + titles, and `server.mcp_config.env` keys). Output filenames are `dist/mcp-<brand>-V.mcpb`.
- **Why:** mcpb is a customer-facing artifact distinct from the PyPI wheel and carries its own brand-bearing surfaces (display_name, user_config field titles, env-var keys in `server.mcp_config.env`). Without templating, TP customers installing the mcpb would see "Hydrolix" in their AI-tool installer UI.
- **Alternatives:** Maintain two `manifest.json` files — rejected, drift surface. Post-build sed pass — rejected, brittle (key names appear in multiple structural positions).
- **Binding:** The mcpb manifest produced in TP mode MUST contain zero instances of the literal `hydrolix` (case-insensitive) in any customer-facing field (`name`, `display_name`, `description`, `user_config` keys/titles, `server.mcp_config.env` keys); source/account-level fields (`homepage`, `repository`, `author`) MAY reference the `hydrolix` org since the bundle ships under the same account and the `github.com/hydrolix/mcp-trafficpeak` repo. An assertion in the build pipeline checks the customer-facing fields.

## Risks / Trade-offs

- [Customer pastes a mixed snippet (`--with mcp-trafficpeak` + `HYDROLIX_*` env vars)] → Both prefixes are accepted (dual-namespace-precedence); startup log line names the brand published in the wheel and the env-var namespace actually used, so support can diagnose.
- [Hatchling hook mutates the wheel in ways not visible by reading `pyproject.toml`, surprising contributors] → Hook lives in one discoverable file (`hatch_build.py`); document in its top docstring that the canonical way to inspect each wheel's metadata is `unzip -p dist/*.whl '*/METADATA'`.
- [Forgetting to set `MCP_BRAND` produces a default-branded wheel, masking a TP build failure] → CI explicitly sets `MCP_BRAND` per step; hook default is `hydrolix` so a missing env var preserves today's behavior on the Hydrolix path; the parity assertion catches a missing TP output before any upload.
- [`mcp-trafficpeak` GAR repo not provisioned in time] → Treated as release-blocking ops prereq separate from code; tracked in tasks/rollout phase.
- [TP wheel and Hydrolix wheel drift at release time] → Both wheels are built from the same source commit of this repo: the Hydrolix wheel by this repo's `publish` job, the TP wheel by the sibling's workflow checking out this repo at the same tag. Both wheels carry the identical version string derived from the tag. Parity verification is post-release (task 7.5) because the sibling's publish is asynchronous from this repo's workflow.
- [Sibling repo workflow fails, hangs, or is missed] → This repo's dispatch step fails the release if the dispatch API call itself fails. If the dispatch is accepted but the sibling's workflow errors mid-build, the post-release verification step (task 7.5) catches the missing TP wheel; the dual brand is then partially released until the sibling workflow is rerun (`gh workflow run publish.yml -R hydrolix/mcp-trafficpeak -f tag=v<v>`). Disaster recovery is one CLI command, hence the choice of `workflow_dispatch` over `repository_dispatch`.

## Rollout Plan

The change is additive — no existing surface is migrated, removed, or behaviorally altered on the Hydrolix path. The rollout sequence is therefore the build-up of the new TP surface alongside the unchanged Hydrolix one.

- Bootstrap the sibling repo — create `hydrolix/mcp-trafficpeak`, populate it with its publish workflow, GitHub-visitor `README.md`, and issue template; provision the `mcp-trafficpeak` PyPI Trusted Publisher binding and the `mcp-trafficpeak` GAR repo. None of these block the hatch-hook / runtime work in this repo; they gate only the first dual release.
- Land the hook — merge this change to `main`. The next release publishes the Hydrolix wheel + mcpb + Docker image as before, additionally fires the sibling dispatch, and pairs the TP mcpb + TP Docker.
- Smoke-test both wheels locally — install each into a clean uv environment, run the server, confirm the baked brand reports correctly in the log line + `User-Agent` + FastMCP server name + admin-comment User token.

**Rollback:** disable the sibling repo's publish workflow; revert this repo's `publish.yml` dispatch step and the TP mcpb/Docker pairing. The Hydrolix path is unchanged throughout, so no Hydrolix-side rollback is required.

## Open Questions

- Should the Hydrolix path emit a deprecation log to TP-deployed customers eventually, or stay silent indefinitely? (Assumed: silent indefinitely.)
