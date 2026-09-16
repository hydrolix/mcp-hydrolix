"""Every registered tool is read-only unless it is an acknowledged write tool (HDX-12410).

Scenario names mirror openspec/changes/gateway-hardening/specs/write-tool-policy.
"""

from __future__ import annotations

import pytest

from mcp_hydrolix.mcp_server import WRITE_TOOLS_REQUIRING_CONFIRMATION, mcp


@pytest.fixture(scope="module")
async def registered_tools():
    return {tool.name: tool for tool in await mcp.list_tools()}


async def test_every_registered_tool_is_read_only(registered_tools):
    assert registered_tools, "no tools registered"
    for name, tool in registered_tools.items():
        if name in WRITE_TOOLS_REQUIRING_CONFIRMATION:
            continue
        assert tool.annotations is not None, f"{name} has no annotations"
        assert tool.annotations.readOnlyHint is True, f"{name} is not marked read-only"
        assert tool.annotations.destructiveHint is False, f"{name} is marked destructive"


async def test_write_tools_declare_destructive_hint(registered_tools):
    unknown = WRITE_TOOLS_REQUIRING_CONFIRMATION - set(registered_tools)
    assert not unknown, f"write-tool policy names unregistered tools: {sorted(unknown)}"
    for name in WRITE_TOOLS_REQUIRING_CONFIRMATION:
        annotations = registered_tools[name].annotations
        assert annotations is not None and annotations.destructiveHint is True, (
            f"{name} is a write tool but does not declare destructiveHint=True"
        )
