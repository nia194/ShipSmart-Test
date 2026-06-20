"""Live e2e for the compliance + workflow lifecycle (UC2/UC3/UC4).

Drives ShipSmart-API's `/compliance/check` and `/workflow/*` against the running
stack (hosted by `scripts/run-stack.sh up`, which sets `WORKFLOW_ENABLED=true`).
SKIPs when the API is down, like the other e2e suites.

The stack is keyless with the KB auto-ingested, so whether a high-risk area is
"unverified" depends on lexical coverage — the lifecycle test therefore adapts:
it always exercises the durable read + a `409` conflict, and the full
interrupt → review → resume path whenever the workflow suspends. (The interrupt
logic itself is proven deterministically in ShipSmart-API's hermetic suite.)
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

_DRONE = {
    "origin_country": "US",
    "destination_country": "BR",
    "declared_value_usd": 600,
    "weight_lbs": 3,
    "description": "camera drone with lithium battery",
}

_ADVISORY_VERDICTS = {"action_required", "review_recommended", "advisory"}
_REVIEW = {"determination": "cleared", "note": "e2e review"}


def test_compliance_check_is_advisory(api):
    """UC2: /compliance/check returns an advisory verdict + a decision trail."""
    r = api.post("/api/v1/compliance/check", json=_DRONE)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] in _ADVISORY_VERDICTS
    assert "compliance:plan" in body["decisions"]
    assert body["findings"]  # at least the structural dangerous-goods flag (battery)


def test_workflow_lifecycle(api):
    """UC3/UC4: process → durable GET → (review→resume) or (409 on completed)."""
    r = api.post("/api/v1/workflow/process", json=_DRONE)
    assert r.status_code == 200
    state = r.json()
    assert state["status"] in {"awaiting_review", "completed"}
    assert "workflow:start" in state["decisions"]
    wid = state["workflow_id"]

    # Durable read returns the same persisted state.
    got = api.get(f"/api/v1/workflow/{wid}")
    assert got.status_code == 200
    assert got.json()["status"] == state["status"]

    if state["status"] == "awaiting_review":
        assert state["pending_review_areas"]
        assert "workflow:interrupt:human_review" in state["decisions"]
        done = api.post(f"/api/v1/workflow/{wid}/review", json=_REVIEW)
        assert done.status_code == 200
        body = done.json()
        assert body["status"] == "completed"
        assert body["documents"]
        assert "workflow:resume" in body["decisions"]
        assert "workflow:complete" in body["decisions"]
    else:
        assert state["documents"]
        assert "workflow:complete" in state["decisions"]

    # Reviewing a workflow that is no longer awaiting review is a 409 conflict.
    conflict = api.post(f"/api/v1/workflow/{wid}/review", json=_REVIEW)
    assert conflict.status_code == 409


def test_workflow_unknown_id_404(api):
    assert api.get("/api/v1/workflow/does-not-exist-xyz").status_code == 404
