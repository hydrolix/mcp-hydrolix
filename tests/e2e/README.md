# End-to-end smoke suite

This suite deploys the local working tree's `mcp-hydrolix` to an existing Hydrolix
Kubernetes cluster and exercises each of the four MCP tools against the running
pod through the cluster ingress. It validates **environmental integration** —
container config, ingress auth, ClickHouse reachability from the pod — not deep
business logic.

The MCP protocol layer (initialize handshake, SSE framing, JSON-RPC envelopes)
is exercised through `fastmcp.Client` — the canonical client from the same
library the server is built on, so client/server parity is by construction.
Only the auth-401 test still uses raw `httpx`, because the 401 signal is
clearer at the HTTP layer than as a wrapped fastmcp exception.

It is excluded from default test runs and from the pre-push hook. Four
independent guards are in place:

1. The `end_to_end` pytest marker (registered in `pyproject.toml`).
2. The pre-push hook in `.pre-commit-config.yaml` filters with
   `-m "not integration_clickhouse and not end_to_end"`.
3. CI runs `uv run pytest -m "not end_to_end"` until secrets are populated.
4. A session-scoped env-var guard in `conftest.py` calls `pytest.fail()` on any
   missing required var with a clear remediation hint.

## Prerequisites

- Working `kubectl` access to a Hydrolix cluster with `spec.mcp_hydrolix.enabled = true`.
- A Docker daemon (only when building locally; see *skip build* below).
- `HYDROLIX_USER` and `HYDROLIX_PASSWORD` for an account that can call
  `/config/v1/login` and run queries against the cluster.

## One-time setup

```bash
cp .env.e2e.example .env.e2e
$EDITOR .env.e2e   # fill in HYDROLIX_USER / HYDROLIX_PASSWORD
```

Existing `inno2.env.private` already holds these credentials and is gitignored
under the same pattern; you can copy values from it.

## Default flow (zero config beyond credentials)

```bash
uv run pytest -m end_to_end tests/e2e/
```

This will:

1. Build the local working tree into a Docker image.
2. Push it to `ttl.sh/mcp-hydrolix-e2e-<user>-<branch>-<shortsha>[-dirty]:1h`.
   ttl.sh requires no auth and TTLs the image after one hour.
3. Snapshot the current `spec.containers` value on the
   `hydrolixclusters.hydrolix.io` CR (typically null/absent) to
   `~/.cache/mcp-hydrolix-e2e/<cluster>-<ns>-<ts>.json`. The full
   `spec.containers` map is captured so any sibling container entries are
   restored faithfully.
4. Annotate the CR with an advisory lock so concurrent runs against the same
   cluster fail fast instead of stomping each other.
5. JSON-merge-patch `spec.containers.mcp-hydrolix = {image, tag}` so the
   operator restarts the Deployment with our image.
6. Wait up to `MCP_HYDROLIX_E2E_READY_TIMEOUT` seconds for the rollout.
7. Log in via `POST https://{HYDROLIX_HOST}/config/v1/login` for a bearer token.
8. Run the smoke tests over `/mcp`.
9. Restore the snapshotted CR state and drop the advisory lock — even on
   failure or interrupt.

## Alternative: image already published via publish-feature.yml

```bash
gh workflow run publish-feature.yml --ref il/test/end-to-end-harness
gh run watch

MCP_HYDROLIX_E2E_IMAGE=us-docker.pkg.dev/hdx-art/t/mcp-hydrolix \
MCP_HYDROLIX_E2E_SKIP_BUILD=1 \
  uv run pytest -m end_to_end tests/e2e/
```

The fixture detects ttl.sh by prefix and switches conventions automatically:

| Registry           | Tag convention                                |
| ------------------ | --------------------------------------------- |
| `ttl.sh/...`       | identity in image name; tag is `1h`           |
| anything else      | identity in tag; mirrors `publish-feature.yml` |

You can pin both `MCP_HYDROLIX_E2E_IMAGE` and `MCP_HYDROLIX_E2E_IMAGE_TAG`
explicitly to bypass derivation. To pin only the branch identity that flows
into the derived image/tag (e.g. when running detached HEAD or with
uncommitted changes whose branch you want to override), set
`MCP_HYDROLIX_E2E_BRANCH=<name>`. Both `_derive_image_and_tag` and
`build_and_push.sh` honor this override identically.

## Standalone build helper

`tests/e2e/build_and_push.sh` is a thin shell wrapper around the same image
derivation logic. It prints `export` lines so you can run it once and re-use
the IMAGE/TAG with `MCP_HYDROLIX_E2E_SKIP_BUILD=1`.

## Cleanup behavior

Cleanup is wrapped in `try/finally` and runs even on `SIGINT` or test crash.
The original CR state is captured to disk **before** any patch is applied; if
the in-memory restore path fails, the disk snapshot remains as a manual
recovery aid.

If a previous run crashed before cleanup, the next run may detect the leftover
override and re-apply the snapshot before starting (idempotent recovery). This
detection only fires when the leftover image string contains
`mcp-hydrolix-e2e-` — the prefix used for ttl.sh-derived images. Runs that
override `MCP_HYDROLIX_E2E_IMAGE` to a non-ttl.sh registry leave images that
do not match this heuristic, so leftover state from those runs must be
cleaned up via the manual recovery CLI (see below). The advisory lock is
checked at startup regardless of the registry path, so a stale lock will
always be surfaced.

## Manual recovery

If for some reason the suite leaves the cluster in a patched state and
auto-recovery does not run (e.g. you killed the process while it was holding
the lock), use the standalone CLI:

```bash
uv run python -m tests.e2e._kube cleanup
```

This reads the most recent snapshot from `~/.cache/mcp-hydrolix-e2e/`, restores
the CR, and removes the advisory lock annotation. Flags:

- `--snapshot <path>` — point at an explicit snapshot file instead of the most
  recent under the cache dir.
- `--kubeconfig <path>` — use a specific kubeconfig file (defaults to
  `KUBECONFIG`/`$HOME/.kube/config`).
- `--kube-context <name>` — use a specific kubectl context (defaults to the
  active one). The CLI prints the resolved context to stderr before patching
  so you can abort if the wrong cluster is selected.

## Troubleshooting

- **`pytest.fail` at session start with "missing required env vars":** you ran
  the suite without `HYDROLIX_USER`/`HYDROLIX_PASSWORD`. If you intended to run
  the unit tests instead, re-run with `-m "not end_to_end"`.
- **`advisory lock held by another run`:** another machine or session is mid-run
  against the same cluster. Verify there is no other invocation, then remove
  the `mcp-hydrolix-e2e/lock` annotation from the CR by hand:
  `kubectl annotate hydrolixclusters/<name> mcp-hydrolix-e2e/lock-`.
- **Rollout timeout:** the failure message includes the last observed pod
  statuses. Bump `MCP_HYDROLIX_E2E_READY_TIMEOUT` if you have a slow scheduler.
- **`mcp_hydrolix.enabled` is false:** the suite refuses to flip it. Enable
  MCP via `spec.mcp_hydrolix.enabled` on the CR or run against a different
  cluster.

## Enabling in CI

Once `HYDROLIX_USER` and `HYDROLIX_PASSWORD` (and a kubeconfig + image
registry credentials) are wired into repository secrets, change the CI step in
`.github/workflows/tests.yaml` from `uv run pytest -m "not end_to_end"` back
to `uv run pytest`.
