"""Live e2e against the MCP tool server."""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.e2e


def _call(mcp, name, args):
    return mcp.post("/tools/call", json={"name": name, "arguments": args}).json()


def test_tools_list_exposes_both_tools_with_schema(mcp):
    body = mcp.post("/tools/list").json()
    names = {t["name"] for t in body["tools"]}
    assert {"validate_address", "get_quote_preview"} <= names
    for tool in body["tools"]:
        assert tool["input_schema"]["type"] == "object"
        assert tool["input_schema"]["additionalProperties"] is False


def test_quote_preview_valid(mcp):
    body = _call(mcp, "get_quote_preview", {
        "origin_zip": "90210", "destination_zip": "10001",
        "weight_lbs": 5, "length_in": 12, "width_in": 8, "height_in": 6,
    })
    assert body["success"] is True
    data = json.loads(body["content"][0]["text"])
    assert isinstance(data.get("services"), list) and data["services"]


def test_quote_preview_malformed_rejected_before_execution(mcp):
    body = _call(mcp, "get_quote_preview", {
        "origin_zip": "90210", "destination_zip": "10001",
        "weight_lbs": -1, "length_in": 12, "width_in": 8, "height_in": 6,
    })
    assert body["success"] is False
    assert "weight_lbs" in body["error"]
    assert body["content"] == []


def test_validate_address_valid(mcp):
    body = _call(mcp, "validate_address", {
        "street": "1 Main St", "city": "Los Angeles", "state": "CA", "zip_code": "90001",
    })
    assert body["success"] is True


def test_server_is_read_only(mcp):
    names = {t["name"] for t in mcp.post("/tools/list").json()["tools"]}
    assert names <= {"validate_address", "get_quote_preview"}  # no write/booking tools
