# Maintainers' guide

This document covers tasks that require privileges held by Hydrolix maintainers
— running the end-to-end suite against a live cluster, and cutting a release.
Contributors and users do not need anything here; see the [README](README.md) to
install and use the server.

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

1. **Pick the commit.** The tag must point at a commit that is **on `main`**. Make
   sure `main` is up to date and green.

2. **Confirm the version.** Check that `pyproject.toml` holds the version you
   intend to release:

   ```bash
   uv version --short   # e.g. 0.3.4
   ```

   If it does not match, bump it on `main` first (`uv version <X.Y.Z>` followed
   by `uv lock --no-upgrade`, then commit and push).

3. **Write the release notes and put them in the annotated tag.** This is a
   required, hand-crafted step — see [Release notes are
   required](#release-notes-are-required) for the format. Author the curated
   notes in the tag's annotation message (not a throwaway `-m "Release v0.3.4"`):

   ```bash
   git checkout main && git pull
   git tag -a v0.3.4 -F NOTES.md      # NOTES.md holds the curated changelog
   git push origin v0.3.4
   ```

   Use an *annotated* tag (`-a`), not a lightweight tag. The tag name must match
   `v[0-9]+.[0-9]+.[0-9]+` exactly or the workflow will not trigger. Keep
   `NOTES.md` around — you reuse the same text as the GitHub Release body in
   step 4.

4. **Watch the workflow.** The push fires `Publish release`, which (after
   `prove-main` passes) runs in parallel:

   - **`publish`** — `uv build` and upload to
     [PyPI](https://pypi.org/p/mcp-hydrolix) via Trusted Publishing.
   - **`publish-docker`** — build and push the image to GAR as both
     `us-docker.pkg.dev/hdx-art/t/mcp-hydrolix:v0.3.4` and `:latest`.
   - **`publish-mcpb`** — build the MCPB bundle and attach it to a GitHub
     Release for the tag. If no Release exists yet, it creates one with GitHub's
     **auto-generated notes** (`gh release create --generate-notes`) — treat
     these as a placeholder you overwrite with your curated notes (see [Release
     notes are required](#release-notes-are-required)). If a Release already
     exists, it only uploads the bundle and leaves the body untouched.

   ```bash
   gh run watch
   ```

5. **Automatic version bump.** Once `publish`, `publish-docker`, and
   `publish-mcpb` all succeed, the `bump-version` job commits a
   `Prepare <next> development cycle` change to `main` that bumps the patch
   version in `pyproject.toml` and `uv.lock`. No manual follow-up is needed for
   the version bump; just `git pull` on `main` afterward.

### Release notes are required

**Every release MUST ship hand-crafted release notes.** This is the whole
motivation for this section. The notes must be *curated by a human* — a grouped,
readable changelog written for the reader — not an auto-generated PR-title dump
and never empty.

Both recent tags are **degenerate** and must not be used as templates:

- `v0.3.2` — body is just the bare version string. Empty.
- `v0.3.3` — GitHub's auto-generated "What's Changed" list (one line per merged
  PR, including `Bump …` dependabot churn). This is a raw dump, not curated
  notes.

The **required style** is the hand-written changelog used in the older tag
annotations — see `v0.3.1`, `v0.3.0`, and `v0.2.4` (`git show v0.3.1`). It has:

- A short heading line with the version.
- Changes **grouped by category** — `Added` / `Changed` / `Removed` / `Fixed`
  (Keep-a-Changelog style), or the equivalent `Bug fixes` / `Improvements` /
  `Documentation` grouping in `v0.2.4`. Omit empty groups.
- One bullet per user-visible change, written as a sentence, each citing its PR
  (`(#88)`) and/or Jira ticket (`(HDX-11190)`).
- **Breaking changes called out explicitly** — prefix the bullet with
  `Breaking:` as in `v0.3.0`, and include the upgrade/migration step (e.g. a
  removed or deprecated `HYDROLIX_*` env var).

Example skeleton (`NOTES.md`):

```markdown
## v0.3.4

### Added
- New `…` capability. (#NNN, HDX-NNNNN)

### Changed
- Breaking: removed `HYDROLIX_OLD_VAR`; use `HYDROLIX_NEW_VAR` instead. (#NNN)

### Fixed
- … (#NNN)
```

Where the notes live:

1. **In the annotated tag** — author them there at tag-creation time
   (`git tag -a v0.3.4 -F NOTES.md`, step 3). The tag annotation is the
   canonical record and the practice the older releases followed.
2. **On the GitHub Release** — `publish-mcpb` creates the Release with GitHub's
   `--generate-notes` (the v0.3.3-style dump), which is **not** acceptable as
   the final body. After the run, overwrite it with your curated notes so the
   Release matches the tag:

   ```bash
   gh release edit v0.3.4 --repo hydrolix/mcp-hydrolix --notes-file NOTES.md
   ```

Do not pre-create the GitHub Release with an empty body before the workflow runs
(that is how `v0.3.2` ended up blank). Either let the workflow create it and then
overwrite the body as above, or create it yourself with `--notes-file NOTES.md`.

### After the release

- Confirm the new version is live on [PyPI](https://pypi.org/p/mcp-hydrolix) and
  that the [GitHub Release](https://github.com/hydrolix/mcp-hydrolix/releases)
  exists for the tag, carries your **curated release notes** (not the
  auto-generated dump), and has the MCPB bundle attached.
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
