"""End-to-end coverage for the HDX-11673 execute_query tunables.

These exercise the full chain: an operator build that knows the new
``mcp_hydrolix`` tunables (deployed via the operator-version override) injects an
env var, which the server reads into its query SETTINGS.

They only run when the operator-version override is engaged
(MCP_HYDROLIX_E2E_OPERATOR_IMAGE set) — otherwise the operator reconciling the
cluster may not understand the tunable and the CR patch would be a no-op or be
rejected by CRD validation. Outside that flow they skip.

The signal used is ``timerange_required`` against a real table with a primary
timestamp: by default (operator emits true) a query with no timerange filter is
rejected; after flipping the CR tunable to false and letting mcp-hydrolix
redeploy, the same query succeeds. Testing both directions proves the value
actually flowed operator -> env -> server. ``SELECT 1`` can't exercise this — it
targets no table, so the timerange requirement never applies.
"""

from __future__ import annotations

import os

import pytest
from fastmcp.exceptions import ToolError

from tests.e2e._kube import (
    read_deployment_generation,
    read_mcp_hydrolix,
    restore_mcp_hydrolix,
    set_mcp_connection_tunable,
    wait_for_rollout,
)
from tests.e2e._mcp_client import make_client, wait_for_endpoint_ready


@pytest.mark.end_to_end
class TestOperatorTunablesEndToEnd:
    async def test_timerange_required_tunable_flows_through(
        self, _e2e_env_guard, mcp_ready, bearer_token
    ) -> None:
        cfg = _e2e_env_guard
        if not cfg.operator_image:
            pytest.skip(
                "operator-version override not engaged "
                "(set MCP_HYDROLIX_E2E_OPERATOR_IMAGE to a build with the new tunables)"
            )

        clients = mcp_ready.clients
        ctx = mcp_ready.ctx
        host = mcp_ready.hydrolix_host
        expected_full = f"{mcp_ready.expected_image}:{mcp_ready.expected_tag}"

        def wait_for_redeploy(min_generation: int | None) -> None:
            wait_for_rollout(
                clients,
                ctx,
                deployment_name=cfg.deployment_name,
                timeout=cfg.ready_timeout,
                min_generation=min_generation,
                expected_image=expected_full,
            )
            wait_for_endpoint_ready(host, bearer_token, timeout=cfg.ready_timeout)

        # A real db.table with a primary timestamp, so the timerange requirement
        # actually applies. Configurable for clusters without the sample dataset;
        # must NOT be a system database (those aren't queryable in Hydrolix).
        table = os.environ.get("MCP_HYDROLIX_E2E_TIMERANGE_TABLE", "sample.sample")
        no_timerange_query = f"SELECT * FROM {table} LIMIT 1"

        # Baseline: the operator defaults timerange_required to true, so a query
        # with no timerange filter must be rejected with a timerange error before
        # we change anything. This confirms the requirement is in force (and that
        # the operator is emitting the env var) to begin with.
        async with make_client(host, bearer_token) as client:
            with pytest.raises(ToolError, match="(?i)time ?range"):
                await client.call_tool("run_select_query", {"query": no_timerange_query})

        # Capture the entire original mcp_hydrolix block so teardown restores the
        # CR to its exact pre-test shape (removing the block when it was absent),
        # rather than leaving empty hydrolix_connection residue behind.
        original_block = read_mcp_hydrolix(clients.custom, ctx)

        # Capture the pre-patch generation BEFORE mutating the CR so the rollout
        # wait isn't satisfied by the current pods.
        pre_gen = read_deployment_generation(clients, ctx, cfg.deployment_name)
        try:
            set_mcp_connection_tunable(clients.custom, ctx, "timerange_required", False)
            wait_for_redeploy(pre_gen)

            async with make_client(host, bearer_token) as client:
                result = await client.call_tool("run_select_query", {"query": no_timerange_query})
            assert not result.is_error, (
                "with timerange_required=False a no-timerange query should succeed, "
                f"but run_select_query reported is_error: {result!r}"
            )
        finally:
            # Restore the original block exactly (no residue), then wait for the
            # resulting redeploy to settle.
            restore_gen = read_deployment_generation(clients, ctx, cfg.deployment_name)
            restore_mcp_hydrolix(clients.custom, ctx, original_block)
            try:
                wait_for_rollout(
                    clients,
                    ctx,
                    deployment_name=cfg.deployment_name,
                    timeout=cfg.ready_timeout,
                    min_generation=restore_gen,
                    expected_image=expected_full,
                )
            except Exception:
                # Best-effort restore; the session-scoped teardown still restores
                # the container override and releases the lock.
                pass
