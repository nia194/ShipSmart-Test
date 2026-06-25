"""Live e2e for the shipping-scope policy + the compliance-explicit switch.

Both behaviors are deployment-configurable, and the run-stack API honors
``SHIPPING_SCOPE`` / ``COMPLIANCE_EXPLICIT_ENABLED`` (default ``worldwide`` /
``true``). Rather than assume a mode, these tests read what the running stack
actually published and assert the behavior matches it — so they pass against
either configuration (and still SKIP when the API is down).

The enforcement logic itself is proven deterministically in ShipSmart-API's
hermetic suite; here we prove the wire behavior end to end.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

_CROSS_BORDER = {
    "origin_country": "US",
    "destination_country": "BR",
    "declared_value_usd": 600,
    "weight_lbs": 3,
    "description": "camera drone",
}
_DOMESTIC = {**_CROSS_BORDER, "destination_country": "US"}
_ADVISORY_VERDICTS = {"action_required", "review_recommended", "advisory"}


def test_info_publishes_shipping_scope(api):
    """The API publishes the active mode so the frontend + siblings can read it."""
    info = api.get("/api/v1/info").json()
    assert info["shipping_scope"] in {"worldwide", "domestic"}
    assert "domestic_country" in info


def test_cross_border_matches_published_scope(api):
    """A US->BR shipment is rejected (422) iff the deployment is domestic-only."""
    scope = api.get("/api/v1/info").json()["shipping_scope"]
    r = api.post("/api/v1/compliance/check", json=_CROSS_BORDER)
    if scope == "domestic":
        assert r.status_code == 422
    else:
        assert r.status_code == 200
        assert r.json()["verdict"] in _ADVISORY_VERDICTS


def test_domestic_shipment_always_in_scope(api):
    """A US->US shipment is accepted regardless of the scope mode."""
    r = api.post("/api/v1/compliance/check", json=_DOMESTIC)
    assert r.status_code == 200
    assert r.json()["verdict"] in _ADVISORY_VERDICTS


def test_compliance_explicit_switch_reflected_in_workflow_trail(api):
    """The workflow trail reflects whether the explicit compliance pass ran.

    Uses a US->US shipment so it stays in scope under either deployment mode.
    """
    state = api.post("/api/v1/workflow/process", json=_DOMESTIC).json()
    decisions = state["decisions"]
    if "workflow:compliance:explicit_skipped" in decisions:
        # Explicit pass off: the hard compliance stage did not run.
        assert not any(d == "compliance:plan" for d in decisions)
        assert state.get("compliance") is None
    else:
        # Explicit pass on (default): the compliance stage produced a summary.
        assert state.get("compliance") is not None
