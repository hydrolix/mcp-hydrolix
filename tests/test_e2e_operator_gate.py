"""Meta-unit tests for the e2e operator-version-override safety gate.

These exercise the pure presence-check helper only (no cluster, no marker), so
they run in the normal (`not end_to_end`) suite. The cluster-name *match* for
the ack is enforced in the ``operator_state`` fixture and is covered by the live
e2e run, not here.
"""

from __future__ import annotations

from tests.e2e.conftest import operator_override_missing_keys


def test_no_override_requested_is_satisfied() -> None:
    # No OPERATOR_IMAGE => override never engages, regardless of the other keys.
    assert operator_override_missing_keys(None, None, None) == []
    assert operator_override_missing_keys("", "operator", "hdx") == []


def test_image_alone_is_blocked() -> None:
    # A bare OPERATOR_IMAGE can never engage the override.
    assert operator_override_missing_keys("op:img", None, None) == [
        "MCP_HYDROLIX_E2E_OPERATOR_DEPLOYMENT",
        "MCP_HYDROLIX_E2E_OPERATOR_OVERRIDE_ACK",
    ]


def test_missing_deployment_is_blocked() -> None:
    assert operator_override_missing_keys("op:img", None, "hdx") == [
        "MCP_HYDROLIX_E2E_OPERATOR_DEPLOYMENT"
    ]


def test_missing_ack_is_blocked() -> None:
    assert operator_override_missing_keys("op:img", "operator", None) == [
        "MCP_HYDROLIX_E2E_OPERATOR_OVERRIDE_ACK"
    ]


def test_all_keys_present_is_satisfied() -> None:
    # Presence gate passes; the ack/cluster-name match is checked later in
    # operator_state.
    assert operator_override_missing_keys("op:img", "operator", "hdx") == []
