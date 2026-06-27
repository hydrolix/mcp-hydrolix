# Maintainers' guide

This document covers tasks that require Hydrolix maintainer privileges: running
the end-to-end suite against a live cluster, and cutting a release. Contributors
and users do not need anything here; see the [README](README.md) to install and
use the server.

## End-to-end tests

The suite under `tests/e2e/` deploys your local working tree to a live Hydrolix
Kubernetes cluster and smoke-tests the MCP tools against the running pod. It
requires `kubectl` access to a deployed cluster with
`spec.mcp_hydrolix.enabled = true`, plus credentials for that cluster. The
`end_to_end` pytest marker keeps it out of default test runs and the pre-push
hook; pass `-m end_to_end` to opt in.

[`tests/e2e/README.md`](tests/e2e/README.md) is the full runbook: what the
suite covers and the guards that keep it out of normal runs, prerequisites and
one-time setup, the default build-and-deploy flow, the `publish-feature.yml`
alternative, the gated operator-version override, cleanup, manual recovery, and
troubleshooting.

## Releasing a new version

Releases are fully automated by [`.github/workflows/publish.yml`](.github/workflows/publish.yml),
which triggers on **pushing an annotated tag** matching `vMAJOR.MINOR.PATCH`
(e.g. `v0.3.4`). The version number lives in `pyproject.toml` and is managed
with `uv version`. Between releases `main` already carries the next patch
version (the previous release's `bump-version` job sets it), so the tag you push
must match the version currently on `main`.

### Steps

1. **Pick the commit.** The tag must point at a commit that is **on `main`**. Make
   sure `main` is up to date and green.

2. **Confirm the version.** Check that `pyproject.toml` holds the version you
   intend to release:

   ```bash
   uv version --short   # e.g. 0.3.4
   ```

   If it does not match, bump it on `main` first (`uv version <X.Y.Z>` followed
   by `uv lock --no-upgrade`, then commit and push).

3. **Write the release notes into the annotated tag.** The tag annotation is the
   source of truth for the notes (see [Release notes are
   required](#release-notes-are-required) for the format). `git tag -a` opens
   your editor so you write them inline:

   ```bash
   git checkout main && git pull
   git tag -a v0.3.4        # opens $EDITOR; write the curated notes as the message
   git push origin v0.3.4
   ```

   Use an *annotated* tag (`-a`), not a lightweight tag. The tag name must match
   `v[0-9]+.[0-9]+.[0-9]+` or the workflow will not trigger.

4. **Watch the workflow.** The push fires `Publish release`, which (after
   `prove-main` passes) runs in parallel:

   - **`publish`**: `uv build` and upload to
     [PyPI](https://pypi.org/p/mcp-hydrolix) via Trusted Publishing.
   - **`publish-docker`**: build and push the image to GAR as both
     `us-docker.pkg.dev/hdx-art/t/mcp-hydrolix:v0.3.4` and `:latest`.
   - **`publish-mcpb`**: build the MCPB bundle and attach it to the GitHub
     Release for the tag. If no Release exists yet, it creates one with the body
     taken from your tag annotation (`--notes-from-tag`). If a Release already
     exists, it uploads the bundle and leaves the body untouched.

5. **Automatic version bump.** Once `publish`, `publish-docker`, and
   `publish-mcpb` all succeed, the `bump-version` job commits a
   `Prepare <next> development cycle` change to `main` that bumps the patch
   version in `pyproject.toml` and `uv.lock`. The bump needs no manual
   follow-up.

### Release notes are required

**Every release MUST ship release notes.** Curate them by hand into a grouped,
readable changelog written for the reader, not an auto-generated PR-title dump
or an empty body.

> [!IMPORTANT]
> The notes have a single source: the **annotated tag message**. Write them
> there and the rest follows: `publish-mcpb` creates the GitHub Release with its
> body taken from the tag annotation (`--notes-from-tag`). You do not set notes
> anywhere else, and there is nothing to copy or re-paste after the run.

Follow [Keep a Changelog](https://keepachangelog.com/): group changes under
`Added` / `Changed` / `Removed` / `Fixed`, one bullet per user-visible change
written as a sentence and citing its PR (`(#88)`) and/or Jira ticket
(`(HDX-11190)`). Prefix breaking changes with `Breaking:` and include the
upgrade/migration step (e.g. a removed or deprecated `HYDROLIX_*` env var). The
older tag annotations (`v0.3.1`, `v0.3.0`, `v0.2.4`; e.g. `git show v0.3.1`) are
good examples.

Example annotation:

```markdown
## v0.3.4

### Added
- New `…` capability. (#NNN, HDX-NNNNN)

### Changed
- Breaking: removed `HYDROLIX_OLD_VAR`; use `HYDROLIX_NEW_VAR` instead. (#NNN)

### Fixed
- … (#NNN)
```

> [!WARNING]
> Do not pre-create the GitHub Release before the workflow runs. The workflow
> only sets the body when it creates the Release, so a Release you make by hand
> keeps whatever body you gave it. You only need to push an annotated tag with
> curated notes; let the workflow create the Release.

### After the release

- Confirm the new version is live on [PyPI](https://pypi.org/p/mcp-hydrolix) and
  that the [GitHub Release](https://github.com/hydrolix/mcp-hydrolix/releases)
  exists for the tag, carries your curated release notes, and has the MCPB
  bundle attached.
- Verify the install path works end to end: install the published version from
  PyPI in a clean environment and confirm the server starts.

## Publishing a feature-branch image (for testing)

To get a Docker image for a branch without cutting a release (e.g. to run the
e2e suite against a pre-built image), trigger
[`publish-feature.yml`](.github/workflows/publish-feature.yml) by hand:

```bash
gh workflow run publish-feature.yml --ref <your-branch>
gh run watch
```

It pushes `us-docker.pkg.dev/hdx-art/t/mcp-hydrolix:branch-<branch>-<shortsha>`.
This never touches PyPI, `:latest`, or the version number. The built image can
be deployed to a Hydrolix cluster for manual testing.
