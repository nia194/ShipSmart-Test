"""Contract: ShipSmart-API tool policy <-> ShipSmart-MCP served tools (guardrails §5.4/§5.5).

The API's agent planner is only as safe as its coverage: every tool MCP serves
must have a policy, and the API must not police a tool MCP doesn't serve (a stale
policy). Parsed from source — no services.
"""

from __future__ import annotations

from sibling import api_tool_policy_names, mcp_tool_names


def test_api_tool_policy_matches_mcp_served_tools():
    policed = api_tool_policy_names()
    served = mcp_tool_names()
    assert policed, "no tool policies found in ShipSmart-API"
    assert served, "no served tools found in ShipSmart-MCP"
    missing_policy = served - policed
    stale_policy = policed - served
    assert not missing_policy, f"MCP tools with no API policy: {sorted(missing_policy)}"
    assert not stale_policy, f"API policies for tools MCP does not serve: {sorted(stale_policy)}"
