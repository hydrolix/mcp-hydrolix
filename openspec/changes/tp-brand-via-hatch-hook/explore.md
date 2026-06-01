*Resolved 5 decisions; 2 assumptions; 1 item deferred.*

## Questions Asked

<!-- Paraphrased audit trail of the interactive exchange that shaped this change. The operator drove every resolution by correcting an in-flight draft; each bullet captures the implicit question that exchange settled. -->

- Build mechanism — should the TP wheel come from sibling `pyproject.toml` configs, a CI-only rewrite script, a thin shim package, or a Hatchling metadata build hook?
- Runtime env-var precedence — when both `TRAFFICPEAK_*` and `HYDROLIX_*` are set, do we compare per-variable, or run two whole resolution chains sequentially?
- Customer-facing docs in this repo — should `README.md` carry both Hydrolix and TrafficPeak install snippets, or only the Hydrolix one?
- Artifact parity — does the TP brand cover only the PyPI wheel, or every release artifact this repo produces (wheel, mcpb, Docker image, anything added later)?
- TP PyPI publication mechanism — PyPI rejects a Trusted Publisher request to publish `mcp-trafficpeak` from `hydrolix/mcp-hydrolix` ("Invalid repository name"). uvx is the canonical TP-customer install path, so we cannot drop PyPI. How do we publish the TP wheel without violating the single-source guarantee?

## Decisions

### Decision: approach-hatchling-hook

- **Question:** How do we produce two PyPI distributions (`mcp-hydrolix`, `mcp-trafficpeak`) from a single source tree?
- **Answer:** Use a custom Hatchling metadata build hook (`hatch_build.py`) keyed on the env var `MCP_BRAND={hydrolix|trafficpeak}`. The hook rewrites `project.name`, `[project.scripts]`, `project.urls`, author/description, and bakes `__brand__` into a small in-package module. CI invokes `uv build` twice per release.
- **Rationale:** Sibling `pyproject.toml` files maximize drift surface (every shared field hand-mirrored forever); CI-only rewrite scripts can't be reproduced on a developer laptop with `uv build`; shim-package approaches re-leak `mcp-hydrolix` into TP lockfiles via transitive deps; `uv_build` intentionally rejects dynamic `project.name`. The Hatchling hook is the only option that gives single-source guarantees, local reproducibility, and one discoverable file as the divergence chokepoint.
- **Affects:** `specs/mcp-server-branding/spec.md → Requirement: Two PyPI Distributions Built From One Source Via A Build-Time Brand Flag`, `design.md → Decision: hatchling-hook`

### Decision: env-var-namespace-chain

- **Question:** When both `TRAFFICPEAK_*` and `HYDROLIX_*` are set at runtime, do we compare per-variable (e.g. `TRAFFICPEAK_HOST` vs `HYDROLIX_HOST`) or run two complete resolution chains with whole-chain precedence?
- **Answer:** Run the full configuration resolver — including the four-tier precedence chain introduced by the sibling `hydrolix-url-config-collapse` change — once over the entire `TRAFFICPEAK_*` namespace. If it yields a usable config (layer-1 anchor present), use that result and ignore `HYDROLIX_*` entirely. Otherwise re-run the same resolver over `HYDROLIX_*`. The two namespaces MUST NOT interleave per-variable.
- **Rationale:** Per-variable interleaving is pathological — a customer who sets `TRAFFICPEAK_URL` but inherits an env-baked `HYDROLIX_HTTP_QUERY_HOST` from a launcher would silently get a half-TP / half-Hydrolix config pointing at two different clusters. Whole-chain semantics keep the two brands as mutually-exclusive configurations and let the existing resolver implementation be reused under a thin namespace-parameter wrapper.
- **Affects:** `specs/mcp-server-branding/spec.md → Requirement: Dual-Namespace Env-Var Contract With Whole-Chain Precedence`, `design.md → Decision: dual-namespace-precedence`

### Decision: docs-hydrolix-only-in-repo

- **Question:** Should this repo's `README.md` document the TrafficPeak-branded install snippet alongside the Hydrolix one, or only the Hydrolix one?
- **Answer:** Only the Hydrolix one. TrafficPeak-branded install snippets and `TRAFFICPEAK_*` env-var documentation live in TrafficPeak-specific customer documentation maintained outside this repository. No customer-facing file in this repo references TrafficPeak.
- **Rationale:** This repo's `README.md` is published verbatim to PyPI as the `mcp-hydrolix` distribution's landing page and is read by Hydrolix-direct customers. Surfacing TP branding there leaks the dual-brand reality into the Hydrolix-customer surface — the inverse of the leak HDX-11476 is fixing. Keeping the two customer surfaces strictly partitioned at the doc layer is cheaper than any rendering / conditional-include scheme.
- **Affects:** `specs/mcp-server-branding/spec.md → Requirement: This Repository's Customer-Facing Documentation References Only The Hydrolix Brand`, `design.md → Decision: docs-hydrolix-only`

### Decision: artifact-parity-invariant

- **Question:** Does the TP brand apply only to the PyPI wheel, or to every release artifact this repo emits?
- **Answer:** Every release artifact, at the same version, from the same source commit. Today's surface is the PyPI wheel + sdist, the mcpb bundle, and the Docker image pushed to GAR. After this change, all three are emitted under both brands; the in-repo artifacts (mcpb, Docker) pair within this repo's release workflow, and the PyPI TP wheel ships from the sibling repo as a `workflow_dispatch`-triggered counterpart of this repo's Hydrolix PyPI publish (see Decision: tp-pypi-via-sibling-repo). Any future release-time artifact added MUST satisfy the same invariant on day one.
- **Rationale:** Version skew between the two brands is the failure mode the dual distribution exists to prevent. A customer support call referencing `mcp-trafficpeak==0.4.0` must be answerable by checking out `v0.4.0` of this repo; that promise has to be enforced by CI structure, not goodwill. Pairing every artifact-producing CI step is the cheapest enforcement mechanism, and asserting both outputs exist post-build catches new artifact types added by future PRs.
- **Affects:** `specs/mcp-server-branding/spec.md → Requirement: Artifact Parity Invariant`, `specs/mcp-server-branding/spec.md → Requirement: Mcpb Bundle Is Brand-Parameterized`, `design.md → Decision: artifact-parity`

### Decision: tp-pypi-via-sibling-repo

- **Question:** PyPI rejects a Trusted Publisher request that would let `hydrolix/mcp-hydrolix`'s release workflow publish a second project (`mcp-trafficpeak`) — the error is "Invalid repository name", a PyPI-side rule that the publishing repo name should match the project name. uvx is the canonical TP-customer install path, so the TP wheel must reach PyPI. How do we publish it without forking source or risking version skew?
- **Answer:** Create a minimal sibling repo `hydrolix/mcp-trafficpeak` whose sole responsibility is publishing identity bound to the `mcp-trafficpeak` name. Its workflow listens for `workflow_dispatch` fired by this repo's `publish.yml`, checks out `hydrolix/mcp-hydrolix@<tag>`, runs `MCP_BRAND=trafficpeak uv build`, and publishes via its own Trusted Publisher config. The hatchling hook in this repo applies a brand-substitution filter to this repo's `README.md` at build time and uses the result as the wheel's `long_description`, so the `mcp-trafficpeak` PyPI landing page is *generated* from this repo's single-source README rather than maintained as a vendored file in the sibling. The sibling owns:
    - the publish workflow
    - its own `README.md` (short — explains why the repo exists and how the dispatch flow works; for GitHub visitors only)
    - the PyPI Trusted Publisher config
    - an issue-triage template

  It does not own:
    - any vendored customer-facing readme (generated at publish time)
    - Python source
    - tests
    - mcpb templates
    - Docker configuration
- **Rationale:** The "publishing identity" framing is what makes the cut principled: the sibling exists *because* PyPI's project-name and repo-name identities are coupled in TP, and the README PyPI renders is logically tied to the same identity. The same framing generalizes — any external surface that binds the `mcp-trafficpeak` *name* (registry manifests for MCP-aware tooling, marketplace listings, future identity tokens) belongs in the sibling, on the same reasoning that put PyPI there. Surfaces whose identity is bound to the source repo for arbitrary reasons (mcpb attached to GitHub Releases on this repo, Docker images in GAR whose repo name is configurable) do not. The dispatch mechanism is `workflow_dispatch` (not `repository_dispatch`) because it targets a named workflow, takes typed inputs (the tag), and is also fireable manually via `gh workflow run` for disaster recovery. Drift is structurally impossible because the sibling has no source to drift from.
- **Affects:** `design.md → Decision: tp-pypi-via-sibling-repo`, `design.md → Decision: hatchling-hook` (README path env var), `design.md → Decision: artifact-parity` (PyPI bullet), `specs/mcp-server-branding/spec.md → Requirement: Two PyPI Distributions Built From One Source Via A Build-Time Brand Flag`, `specs/mcp-server-branding/spec.md → Requirement: Artifact Parity Invariant`, `specs/mcp-server-branding/spec.md → Requirement: Sibling Repo Scope Is Restricted To Publishing Identity`, `tasks.md → Phase 4`, `tasks.md → Phase 5`

## Deferred / Out of Scope

- TP-branded customer-facing documentation — owned outside this repo; this change ships the artifacts that documentation will reference.

## Assumptions

- The sibling `hydrolix-url-config-collapse` change lands before or alongside this one — its four-tier precedence resolver is what the dual-namespace wrapper composes over. If sequencing slips, this change's resolver-wrapper task gates on the sibling.
- The Python import path stays `mcp_hydrolix` for both wheels — if a future TP customer demands the import path also be TP-branded, that is a separate (and much larger) change. (This is NOT a user-visible surface — it's what people would use if they wanted to load the *source code* of `mcp_hydrolix` into another application).
