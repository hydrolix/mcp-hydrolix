*Defines how the local MCP server's distribution name, console-script, runtime brand identifier, env-var contract, User-Agent, and release artifacts are determined per brand.*

## ADDED Requirements

### Requirement: Two PyPI Distributions Built From One Source Via A Build-Time Brand Flag

Two PyPI distributions, `mcp-hydrolix` and `mcp-trafficpeak`, SHALL be released together at the same version string, both built from the same source revision *of this repository*. The selection between brands at build time SHALL be controlled exclusively by an environment variable `MCP_BRAND` with the literal values `hydrolix` or `trafficpeak` (default: `hydrolix`). A custom Hatchling build hook (in `hatch_build.py` adjacent to `pyproject.toml`) SHALL be the single chokepoint that mutates wheel metadata based on `MCP_BRAND`. Sibling or parallel `pyproject.toml` files MUST NOT be introduced; the two distributions MUST NOT diverge in dependencies, version, or any other shared field. The `mcp-hydrolix` distribution is published by this repo's release workflow; the `mcp-trafficpeak` distribution is published by the sibling repo `hydrolix/mcp-trafficpeak` (which checks out this repo at the release tag) per Requirement: Only Pypi Publishing Goes Through The Sibling Repo.

<!-- settle: explore/approach-hatchling-hook -->
<!-- settle: explore/tp-pypi-via-sibling-repo -->

#### Scenario: Default Build Produces The Hydrolix Wheel

- **WHEN** a developer or CI job runs `uv build` with no `MCP_BRAND` set
- **THEN** the produced wheel has distribution name `mcp-hydrolix` and the console-script `mcp-hydrolix`, identical to today's behavior

#### Scenario: Trafficpeak Build Via Env Var Produces The Tp Wheel

- **WHEN** a developer or CI job runs `MCP_BRAND=trafficpeak uv build`
- **THEN** the produced wheel has distribution name `mcp-trafficpeak`, console-script `mcp-trafficpeak`, the same source commit hash, and the same version string as a Hydrolix-mode build from the same checkout

#### Scenario: Invalid Mcp Brand Value Fails Fast

- **WHEN** `uv build` is invoked with `MCP_BRAND=foo` (any value other than `hydrolix` or `trafficpeak`)
- **THEN** the build fails with a clear error naming the env var and the two acceptable values, and no wheel is produced

#### Scenario: Tp Wheel Is Built From This Repos Tagged Commit

- **GIVEN** the sibling repo `hydrolix/mcp-trafficpeak`'s publish workflow has been triggered with tag input `v0.4.0`
- **WHEN** the sibling's workflow runs to completion
- **THEN** it has checked out `hydrolix/mcp-hydrolix@v0.4.0` and built `mcp-trafficpeak==0.4.0` from that commit
- **AND** no source file under `mcp_hydrolix/` was loaded from the sibling repo's own contents

### Requirement: Brand-Appropriate Distribution Metadata With Zero Cross-Brand Leakage

The Hatchling build hook SHALL set `project.name`, `[project.scripts]` console-script name, `project.urls`, `project.description`, and `Author`/`Maintainer` fields to brand-appropriate values for the wheel being built. The TrafficPeak wheel's **customer-facing brand-identity** fields — the distribution `Name`, the console-script name, and the `Summary`/description — MUST NOT contain the literal string `hydrolix` (case-insensitive). Two classes of field are exempt: (1) internal Python module / import paths, which are not user-visible; and (2) source/account-level fields (`project.urls` repository links, `Author`/`Maintainer`), which legitimately reference the Hydrolix org because `mcp-trafficpeak` is published under the same PyPI account and its repository is `github.com/hydrolix/mcp-trafficpeak`. The Hydrolix wheel's distribution metadata MUST NOT contain the literal string `trafficpeak` (case-insensitive) in any field.

<!-- settle: explore/approach-hatchling-hook -->

#### Scenario: Pip Show On Tp Wheel Has No Hydrolix String

- **GIVEN** the TP wheel built with `MCP_BRAND=trafficpeak` has been installed into a fresh virtualenv
- **WHEN** a user runs `pip show mcp-trafficpeak`
- **THEN** the customer-facing brand-identity fields (Name, Summary) do not contain the substring `hydrolix` (case-insensitive), and Name is `mcp-trafficpeak`
- **AND** the source/account-level fields (Home-page / Project-URLs repository link, Author) MAY reference the `hydrolix` org (the package ships under the Hydrolix PyPI account; its repository is `github.com/hydrolix/mcp-trafficpeak`)

#### Scenario: Pip Show On Hydrolix Wheel Is Unchanged

- **GIVEN** the Hydrolix wheel built by the new pipeline has been installed into a fresh virtualenv
- **WHEN** a user runs `pip show mcp-hydrolix`
- **THEN** the output is equivalent to what `pip show mcp-hydrolix` returned for the same version pre-change (modulo the version string), and contains no substring `trafficpeak`

#### Scenario: Uv Tree Shows Only The Installed Brand

- **GIVEN** a project has installed `mcp-trafficpeak` (and not `mcp-hydrolix`)
- **WHEN** a user runs `uv tree` in that project
- **THEN** the dependency listing names `mcp-trafficpeak` and contains no transitive reference to `mcp-hydrolix`

#### Scenario: Long Description Is Generated By The Brand Filter From This Repos Readme

- **GIVEN** this repo's `README.md` exists at the source-tree root
- **WHEN** a wheel is built with `MCP_BRAND=hydrolix`
- **THEN** the wheel's `METADATA` `Description` field contains the contents of `README.md` byte-for-byte (the filter is an identity transform in Hydrolix mode)

#### Scenario: Long Description Tokens Are Rebranded For Trafficpeak Builds

- **GIVEN** this repo's `README.md` contains occurrences of `mcp-hydrolix`, `HYDROLIX_` env-var prefixes, and the prose brand name `Hydrolix`
- **WHEN** a wheel is built with `MCP_BRAND=trafficpeak`
- **THEN** the wheel's `METADATA` `Description` field contains the result of applying the brand-substitution filter to `README.md`
- **AND** every literal `mcp-hydrolix` has become `mcp-trafficpeak`
- **AND** every `HYDROLIX_`-prefixed env var has become `TRAFFICPEAK_`-prefixed
- **AND** the prose brand name `Hydrolix` has been substituted per the per-brand substitution table

### Requirement: Runtime Brand Identifier Baked At Build Time

The build hook SHALL write a module (e.g. `mcp_hydrolix/_brand.py`) into the wheel containing at minimum two constants: `__brand__` equal to either `"hydrolix"` or `"trafficpeak"` (the short identifier) and `__dist_name__` equal to the matching PyPI distribution name (`"mcp-hydrolix"` or `"mcp-trafficpeak"`). The server SHALL determine its runtime brand identifier and runtime distribution name exclusively from these baked constants. The distribution name MUST be used wherever the server identifies itself in customer-visible output:

- the server's startup log line
- the leading token of the `User-Agent` header on all outbound HTTP requests the server makes to the configured cluster API
- the `name=` argument passed to the FastMCP server constructor (the MCP-protocol server-name advertisement)
- the `User` token of the `hdx_query_admin_comment` setting attached to outbound SQL queries

These values MUST NOT be derived from `sys.argv[0]`, from which environment-variable namespace supplied credentials, or from any other runtime-detectable signal. The literal string `"mcp-hydrolix"` MUST NOT appear in customer-visible runtime output produced by a wheel built with `MCP_BRAND=trafficpeak`.

<!-- settle: explore/approach-hatchling-hook -->

#### Scenario: Brand Identifier In Startup Log Reflects Baked Constant

- **GIVEN** a wheel was built with `MCP_BRAND=trafficpeak`
- **WHEN** the server is started from that wheel
- **THEN** the startup log line contains a brand identifier of `trafficpeak`

#### Scenario: Brand Identifier In Outbound User Agent Reflects Baked Constant

- **GIVEN** a wheel was built with `MCP_BRAND=trafficpeak`
- **WHEN** the server makes an outbound HTTP request to its configured cluster
- **THEN** the request's `User-Agent` header begins with `mcp-trafficpeak/<version>`

#### Scenario: Renaming The Launcher Does Not Change The Reported Brand

- **GIVEN** the `mcp-trafficpeak` wheel is installed
- **WHEN** its console-script is invoked via a wrapper that rewrites `argv[0]` to `mcp-hydrolix`
- **THEN** the startup log line and outbound `User-Agent` still report `trafficpeak`

#### Scenario: Fastmcp Server Name Reflects The Baked Distribution Name

- **GIVEN** a wheel was built with `MCP_BRAND=trafficpeak`
- **WHEN** the server initializes its FastMCP instance
- **THEN** the FastMCP server is constructed with `name="mcp-trafficpeak"`
- **AND** an MCP client connecting to the server sees `mcp-trafficpeak` as the server name advertisement

#### Scenario: Admin Comment User Token Reflects The Baked Distribution Name

- **GIVEN** a wheel was built with `MCP_BRAND=trafficpeak`
- **WHEN** the server attaches `hdx_query_admin_comment` to an outbound SQL query
- **THEN** the `User` token in that comment is `mcp-trafficpeak`
- **AND** the literal substring `mcp-hydrolix` does not appear anywhere in the comment

#### Scenario: No Customer-Visible Output Of A Trafficpeak Wheel Contains The Hydrolix Distribution Name

- **GIVEN** a wheel was built with `MCP_BRAND=trafficpeak`
- **WHEN** every customer-visible runtime output path is exercised (startup log line, outbound `User-Agent`, MCP-protocol server-name advertisement, `hdx_query_admin_comment` setting)
- **THEN** none of those outputs contains the substring `mcp-hydrolix` (case-insensitive)

### Requirement: Dual-Namespace Env-Var Contract With Whole-Chain Precedence

The server SHALL accept a `TRAFFICPEAK_*` environment-variable namespace that mirrors the **modern** `HYDROLIX_*` variables one-for-one — every non-deprecated variable consumed by the configuration resolver (including but not limited to `URL`, `TOKEN`, `HTTP_QUERY_HOST` / `PORT` / `SECURE`, `VERSION_API_HOST` / `PORT` / `SECURE`, `VERIFY`, `USER`, `PASSWORD`) MUST be accepted under both prefixes with identical semantics, including identical within-namespace precedence rules. The deprecated `HYDROLIX_*` aliases (`HYDROLIX_HOST`, `HYDROLIX_PORT`, `HYDROLIX_SECURE`, `HYDROLIX_API_HOST`, `HYDROLIX_API_PORT`) are NOT mirrored under `TRAFFICPEAK_*`; the TrafficPeak namespace supports only the modern variable scheme, so `TRAFFICPEAK_URL` is its sole layer-1 anchor. At startup, the server SHALL resolve its effective configuration by first running the full resolver over the `TRAFFICPEAK_*` namespace; if the layer-1 anchor `TRAFFICPEAK_URL` is present the result MUST be used and `HYDROLIX_*` MUST be ignored entirely; otherwise the server SHALL re-run the same resolver over `HYDROLIX_*` (whose layer-1 anchor is `HYDROLIX_URL`, or the deprecated `HYDROLIX_HOST` alias accepted only for stdio transport). The two namespaces MUST NOT interleave on a per-variable basis. If both namespaces independently resolve to different effective values, the server SHALL prefer the TrafficPeak resolution and SHALL emit exactly one WARNING-level log line at startup naming the conflicting layer-1 variables and identifying `TRAFFICPEAK_*` as the winner. Identical effective values → silent. Neither namespace resolves → exit non-zero with an error message naming `TRAFFICPEAK_URL` and `HYDROLIX_URL` as the acceptable layer-1 anchors.

<!-- settle: explore/env-var-namespace-chain -->

#### Scenario: Only Trafficpeak Env Vars Provided

- **GIVEN** `TRAFFICPEAK_URL` is set and no `HYDROLIX_*` variable is set
- **WHEN** the server starts
- **THEN** the server resolves its configuration entirely from `TRAFFICPEAK_*`, starts silently, and uses the TP-namespace cluster identity for all subsequent requests

#### Scenario: Only Hydrolix Env Vars Provided

- **GIVEN** `HYDROLIX_URL` (or an accepted alias) is set and no `TRAFFICPEAK_*` variable is set
- **WHEN** the server starts
- **THEN** the server resolves entirely from `HYDROLIX_*`, starts silently, behaves identically to its pre-change behavior, and emits no warning about absent `TRAFFICPEAK_*` variables

#### Scenario: Partial Trafficpeak Config Falls Through To Hydrolix

- **GIVEN** `TRAFFICPEAK_HTTP_QUERY_HOST` is set, no `TRAFFICPEAK_URL` anchor is set, and `HYDROLIX_URL` is set
- **WHEN** the server starts
- **THEN** the server falls through to the `HYDROLIX_*` namespace, uses `HYDROLIX_URL` and Hydrolix-namespace overrides, and ignores the stray `TRAFFICPEAK_HTTP_QUERY_HOST`

#### Scenario: Both Namespaces Resolve With Conflicting Anchors

- **GIVEN** `TRAFFICPEAK_URL=https://tp.example.live` and `HYDROLIX_URL=https://hdx.example.live` are both set
- **WHEN** the server starts
- **THEN** the server uses the `TRAFFICPEAK_URL` value, emits exactly one WARNING log line naming both variables and identifying `TRAFFICPEAK_*` as the winner, and proceeds normally

#### Scenario: Both Namespaces Resolve To Identical Values

- **GIVEN** `TRAFFICPEAK_URL` and `HYDROLIX_URL` are both set to the same value
- **WHEN** the server starts
- **THEN** the server starts silently with no conflict warning

#### Scenario: Neither Namespace Provides An Anchor

- **GIVEN** none of `TRAFFICPEAK_URL`, `HYDROLIX_URL`, or the deprecated `HYDROLIX_HOST` are set
- **WHEN** the server starts
- **THEN** the server exits non-zero with an error message naming `TRAFFICPEAK_URL` and `HYDROLIX_URL` as the acceptable layer-1 anchors

### Requirement: Existing Hydrolix-Branded Surface Is Preserved

This change MUST NOT remove, rename, or behaviorally alter the `mcp-hydrolix` PyPI distribution, the `mcp-hydrolix` console-script entry point, the `mcp_hydrolix` Python import path, the existing `HYDROLIX_*` environment-variable contract, or any tool the MCP server already exposes. Existing customer configurations using any of the above MUST continue to work with no user-visible behavioral change after this change ships.

#### Scenario: Pre-Change Customer Config Still Works

- **GIVEN** a Hydrolix customer with an unchanged pre-existing MCP config
- **WHEN** they upgrade from the last pre-change release to the first post-change release
- **THEN** their server starts, connects, and serves tools with no observable change in behavior or required env vars

#### Scenario: Python Import Path Is Unchanged

- **GIVEN** either the `mcp-hydrolix` or `mcp-trafficpeak` wheel is installed
- **WHEN** any external code executes `from mcp_hydrolix import ...`
- **THEN** the import succeeds and resolves to the same Python module in both cases

### Requirement: This Repository's Customer-Facing Documentation References Only The Hydrolix Brand

`README.md` and any other customer-facing documentation files co-located in this repository SHALL reference only the Hydrolix-branded install snippet (`mcp-hydrolix` distribution name, `mcp-hydrolix` console-script) and only the `HYDROLIX_*` environment-variable namespace. TrafficPeak-branded install snippets and the `TRAFFICPEAK_*` namespace MUST NOT appear in any customer-facing doc in this repository. Internal engineering documentation (the `openspec/` tree, `CONTRIBUTING.md`, source comments) MAY reference both brands.

<!-- settle: explore/docs-hydrolix-only-in-repo -->

#### Scenario: Readme Does Not Mention Trafficpeak

- **GIVEN** the change has shipped
- **WHEN** a reader greps `README.md` and any other top-level customer-facing doc file for the literal string `trafficpeak` (case-insensitive)
- **THEN** there are zero matches

#### Scenario: Internal Engineering Docs May Mention Both Brands

- **WHEN** a reader greps `openspec/`, `CONTRIBUTING.md`, or source comments for the literal string `trafficpeak`
- **THEN** matches are permitted (this requirement does not constrain those surfaces)

### Requirement: Artifact Parity Invariant

For every release artifact this repository emits under the `mcp-hydrolix` brand at version V, the same release workflow run SHALL emit a corresponding `mcp-trafficpeak` artifact at the identical version V, built from the same source commit. This invariant SHALL hold for the PyPI wheel + sdist, the mcpb bundle, the Docker image pushed to GAR, and any future release-time artifact type introduced to this repository. The release workflow MUST fail before any partial-brand upload completes if either brand's counterpart is missing.

<!-- settle: explore/artifact-parity-invariant -->

#### Scenario: Release Tag Publishes Both Pypi Distributions At The Same Version

- **GIVEN** the release workflow has been triggered in this repo for tag `v0.4.0`
- **WHEN** the workflow chain runs to completion (this repo's `publish` job publishes `mcp-hydrolix`, fires `workflow_dispatch` to `hydrolix/mcp-trafficpeak`, and the sibling's workflow runs to completion)
- **THEN** both `mcp-hydrolix==0.4.0` and `mcp-trafficpeak==0.4.0` are present on PyPI
- **AND** both were built from the same source commit of `hydrolix/mcp-hydrolix` that the tag `v0.4.0` points to

#### Scenario: Sibling Repo Dispatch Failure Fails The Release

- **GIVEN** the `hydrolix/mcp-trafficpeak` repo is unreachable or its publish workflow rejects the dispatch (e.g. missing input, disabled workflow)
- **WHEN** this repo's `publish.yml` reaches the dispatch step
- **THEN** the dispatch step fails, `publish.yml` fails, and no further publishing steps run
- **AND** the recovery path is `gh workflow run publish.yml -R hydrolix/mcp-trafficpeak -f tag=v<v>` once the sibling-side issue is resolved

#### Scenario: Release Tag Publishes Both Mcpb Bundles At The Same Version

- **GIVEN** the release workflow has been triggered for tag `v0.4.0`
- **WHEN** the `publish-mcpb` job runs to completion
- **THEN** `dist/mcp-hydrolix-0.4.0.mcpb` and `dist/mcp-trafficpeak-0.4.0.mcpb` are both produced and both attached to the GitHub Release

#### Scenario: Release Tag Publishes Both Docker Images At The Same Version

- **GIVEN** the release workflow has been triggered for tag `v0.4.0`
- **WHEN** the `publish-docker` job runs to completion
- **THEN** `us-docker.pkg.dev/hdx-art/t/mcp-hydrolix:v0.4.0` (and `:latest`) and `us-docker.pkg.dev/hdx-art/t/mcp-trafficpeak:v0.4.0` (and `:latest`) are both pushed

#### Scenario: Ci Fails If Pairing Is Broken

- **GIVEN** a future PR causes a release-time job to produce only one brand's artifact (or skip the parity assertion)
- **WHEN** the release workflow runs on a tag affected by that PR
- **THEN** the parity assertion fails before any artifact is published, and no partial release is published

### Requirement: Mcpb Bundle Is Brand-Parameterized

`mcpb/build.sh`, `mcpb/manifest.json.tmpl`, and `mcpb/pyproject.toml.tmpl` SHALL accept the same `MCP_BRAND` env var (default `hydrolix`) as the Hatchling build hook. In TrafficPeak mode the produced bundle MUST have `name: mcp-trafficpeak`, brand-appropriate `display_name`, `description`, `long_description`, `author`, `homepage`, `repository`, and `keywords` fields, and a `user_config` block whose field keys and titles reference TrafficPeak (not Hydrolix). The `server.mcp_config.env` block MUST set `TRAFFICPEAK_*` keys (which the server then resolves per the Dual-Namespace Env-Var Contract).

<!-- settle: explore/artifact-parity-invariant -->

#### Scenario: Tp Mode Mcpb Build Emits A Tp-Branded Bundle

- **WHEN** `MCP_BRAND=trafficpeak bash mcpb/build.sh` is invoked at version V
- **THEN** `dist/mcp-trafficpeak-V.mcpb` is produced
- **AND** its `manifest.json` reports `name: mcp-trafficpeak`
- **AND** no customer-facing field (`name`, `display_name`, `description`, `user_config` keys/titles, `server.mcp_config.env` keys) contains the substring `hydrolix` (case-insensitive); source/account-level fields (`homepage`, `repository`, `author`) MAY reference the `hydrolix` org
- **AND** the `user_config` block uses TrafficPeak-prefixed field titles

#### Scenario: Default Mode Mcpb Build Emits The Hydrolix Bundle Unchanged

- **WHEN** `bash mcpb/build.sh` is invoked with no `MCP_BRAND` set at version V
- **THEN** `dist/mcp-hydrolix-V.mcpb` is produced
- **AND** its content is equivalent to today's Hydrolix-branded bundle (modulo the version string)

### Requirement: Only Pypi Publishing Goes Through The Sibling Repo

**The TP PyPI wheel — and the PyPI landing-page content rendered for it — is the ONLY release artifact published through the sibling repository `hydrolix/mcp-trafficpeak`. Every other TP-branded release artifact (mcpb bundle, Docker image, and any future artifact whose distribution surface does not bind the `mcp-trafficpeak` name) MUST publish directly from this repository, paired with its Hydrolix counterpart in the same workflow run.**

<!-- settle: explore/tp-pypi-via-sibling-repo -->

The sibling exists only because PyPI's Trusted Publisher binds project name to source-repo name. The test for whether a future publishing surface joins the sibling is whether that surface binds the `mcp-trafficpeak` *repository name* in the same way; if not, the surface's publishing step stays in this repo.

The sibling repository SHALL contain only artifacts whose identity is bound to the `mcp-trafficpeak` *repository name* on an external publishing surface.

Required at minimum:

- a single publish workflow (`workflow_dispatch` listener that checks out `hydrolix/mcp-hydrolix@<tag>` and runs `MCP_BRAND=trafficpeak uv build`)
- a `README.md` describing the repository's purpose for GitHub visitors (why it exists, how the dispatch flow works)
- the PyPI Trusted Publisher binding
- a GitHub issue-triage template

Permitted as future additions on the same principle: configuration files required by any external surface that binds the `mcp-trafficpeak` name (e.g. registry manifests for MCP-aware tooling, marketplace listings, identity tokens for additional publishing destinations).

The customer-facing PyPI landing-page content for `mcp-trafficpeak` is generated at build time from this repo's `README.md` by the hatchling hook's brand-substitution filter; the sibling MUST NOT vendor a separate `PYPI_README.md` or any other customer-facing readme.

The sibling repo MUST NOT contain:

- Python source under any `mcp_hydrolix/` path
- a `pyproject.toml`
- tests
- mcpb templates
- a `Dockerfile`
- any other source asset of `mcp-hydrolix`

The sibling's `README.md` MUST NOT contain customer install instructions (those reach PyPI via the brand filter applied to this repo's `README.md`). The dispatch mechanism between this repo and the sibling MUST be `workflow_dispatch` (not `repository_dispatch`) targeting the sibling's named publish workflow with the release tag as a typed `string` input.

#### Scenario: Sibling Repo Contains No Source Or Tests

- **WHEN** a reader runs `find . -path ./.git -prune -o \( -name 'pyproject.toml' -o -path '*/mcp_hydrolix/*' -o -path '*/tests/*' -o -name 'Dockerfile' -o -path '*/mcpb/*' \) -print` in a clone of `hydrolix/mcp-trafficpeak`
- **THEN** no paths are printed

#### Scenario: Sibling Repo Publish Workflow Uses Workflow Dispatch

- **WHEN** a reader inspects the sibling repo's publish workflow YAML
- **THEN** the workflow declares `on: workflow_dispatch:` with a required `tag` input typed as `string`
- **AND** no `on: repository_dispatch:` or `on: push:` trigger is configured for releases

#### Scenario: Tp Pypi Landing Page Is Generated From This Repos Readme By The Brand Filter

- **GIVEN** a `mcp-trafficpeak==<v>` release has been published by the sibling repo's workflow
- **WHEN** a user views the `mcp-trafficpeak` project page on PyPI
- **THEN** the rendered project description matches the result of applying the brand-substitution filter to `hydrolix/mcp-hydrolix@v<v>`'s `README.md`
- **AND** it does NOT match the sibling repo's own `README.md` (which describes the repo's purpose, not the product)
- **AND** the sibling repo at the release commit contains no `PYPI_README.md` or equivalent vendored customer-facing readme
