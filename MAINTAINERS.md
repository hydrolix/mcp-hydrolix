# Maintainers' guide

This document covers tasks that require privileges held by Hydrolix maintainers
— running the end-to-end suite against a live cluster, and cutting a release.
Contributors do not need anything here; see the [README](README.md) to install
and use the server, and `tests/e2e/README.md` for the full e2e runbook.

## Who can do this

Releasing and running the e2e suite require operational access that is not
available to outside contributors:

- **PyPI** — release publishing uses Trusted Publishing (OIDC) from the
  `pypi` GitHub Environment; no long-lived token is needed, but the workflow
  and environment are scoped to this repository.
- **Google Artifact Registry** (`us-docker.pkg.dev/hdx-art`) — Docker images are
  pushed using the `GCP_GKE_CI_KEY` repository secret.
- **A live Hydrolix cluster** — the e2e suite deploys the working tree to a real
  Kubernetes cluster and needs `kubectl` access plus query credentials.

## End-to-end tests

A separate suite under `tests/e2e/` deploys the local working tree to a live
Hydrolix Kubernetes cluster and smoke-tests the MCP tools against the running
pod. It exercises **environmental integration** — container config, ingress
auth, ClickHouse reachability from the pod — not deep business logic.

It is excluded from default test runs and from the pre-push hook; running it
requires explicit opt-in via the `end_to_end` pytest marker plus credentials and
`kubectl` access to a cluster with `spec.mcp_hydrolix.enabled = true`.

```bash
cp .env.e2e.example .env.e2e
$EDITOR .env.e2e   # HYDROLIX_USER, HYDROLIX_PASSWORD, MCP_HYDROLIX_E2E_KUBE_CONTEXT
uv run pytest -m end_to_end tests/e2e/
```

See [`tests/e2e/README.md`](tests/e2e/README.md) for the full runbook:
prerequisites, the default build-and-deploy flow, the
`publish-feature.yml`-published-image alternative, the gated operator-version
override, cleanup behavior, manual recovery, and troubleshooting.

## Releasing a new version

Releases are fully automated by [`.github/workflows/publish.yml`](.github/workflows/publish.yml),
which triggers on **pushing an annotated tag** matching `vMAJOR.MINOR.PATCH`
(e.g. `v0.3.4`). The version number lives in `pyproject.toml` and is managed
with `uv version`. Between releases `main` already carries the next patch
version (the previous release's `bump-version` job sets it), so the tag you push
must match the version currently on `main`.

### Steps

1. **Pick the commit.** The tag must point at a commit that is **on `main`** —
   the workflow's first job (`prove-main`) fails the release if the tagged
   commit is not reachable from `origin/main`. Make sure `main` is up to date
   and green.

2. **Confirm the version.** Check that `pyproject.toml` holds the version you
   intend to release:

   ```bash
   uv version --short   # e.g. 0.3.4
   ```

   If it does not match, bump it on `main` first (`uv version <X.Y.Z>` followed
   by `uv lock --no-upgrade`, then commit and push).

3. **Create an annotated tag** for that version and push it:

   ```bash
   git checkout main && git pull
   git tag -a v0.3.4 -m "Release v0.3.4"
   git push origin v0.3.4
   ```

   Use an *annotated* tag (`-a`), not a lightweight tag. The tag name must match
   `v[0-9]+.[0-9]+.[0-9]+` exactly or the workflow will not trigger.

4. **Watch the workflow.** The push fires `Publish release`, which (after
   `prove-main` passes) runs in parallel:

   - **`publish`** — `uv build` and upload to
     [PyPI](https://pypi.org/p/mcp-hydrolix) via Trusted Publishing.
   - **`publish-docker`** — build and push the image to GAR as both
     `us-docker.pkg.dev/hdx-art/t/mcp-hydrolix:v0.3.4` and `:latest`.
   - **`publish-mcpb`** — build the MCPB bundle and attach it to a GitHub
     Release for the tag (creating the Release with generated notes if it does
     not already exist).

   ```bash
   gh run watch
   ```

5. **Automatic version bump.** Once `publish`, `publish-docker`, and
   `publish-mcpb` all succeed, the `bump-version` job commits a
   `Prepare <next> development cycle` change to `main` that bumps the patch
   version in `pyproject.toml` and `uv.lock`. No manual follow-up is needed for
   the version bump; just `git pull` on `main` afterward.

### After the release

- Confirm the new version is live on [PyPI](https://pypi.org/p/mcp-hydrolix) and
  that the [GitHub Release](https://github.com/hydrolix/mcp-hydrolix/releases)
  has the MCPB bundle attached.
- Verify the install path works end to end:

  ```bash
  uvx --python 3.13 --refresh-package mcp-hydrolix mcp-hydrolix --help
  ```

### Rolling back

PyPI releases cannot be overwritten — a version number, once published, is
permanent. If a release is broken:

- **Yank** the bad version on PyPI (it stays downloadable for existing pins but
  is hidden from new resolutions), then release a fixed `PATCH` bump.
- For Docker, the GAR `:latest` tag follows the most recent successful release;
  re-running a good release (or pushing a corrected tag) moves it back.

## Publishing a feature-branch image (non-release)

To get a Docker image for a branch without cutting a release — e.g. to run the
e2e suite against a pre-built image — trigger
[`publish-feature.yml`](.github/workflows/publish-feature.yml) manually:

```bash
gh workflow run publish-feature.yml --ref <your-branch>
gh run watch
```

It pushes `us-docker.pkg.dev/hdx-art/t/mcp-hydrolix:branch-<branch>-<shortsha>`.
This never touches PyPI, `:latest`, or the version number.
