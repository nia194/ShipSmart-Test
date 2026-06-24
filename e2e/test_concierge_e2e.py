"""Live e2e against the Conversational Concierge + the hybrid form ⇄ chat sync.

Proves the round trip the Web ShipmentDraft store relies on: the concierge
clarifies only for missing slots, treats client-sent (form-provided) slots as
satisfied — so it does NOT re-ask — and echoes the full merged state back so the
client can patch the form. Skips when the API isn't hosted.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e

_EMPTY_STATE = {
    "slots": {},
    "intent": None,
    "status": "gathering",
    "pending_clarification": None,
    "turns": 0,
}


def _chat(api, message, state=None):
    return api.post("/api/v1/concierge/chat", json={"message": message, "state": state})


def test_concierge_clarifies_for_a_missing_slot(api):
    r = _chat(api, "I want to ship something")
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"]["status"] == "gathering"
    assert body["clarification"]
    assert any(d.startswith("concierge:clarify:") for d in body["decisions"])


def test_concierge_does_not_reask_form_provided_slots(api):
    # form-provided slots (the hybrid-sync case): compliance already has what it needs.
    state = {
        **_EMPTY_STATE,
        "slots": {"destination_country": "BR", "description": "camera drone with lithium battery"},
        "intent": "compliance",
    }
    r = _chat(api, "is this shipment compliant?", state)
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert not any(d.startswith("concierge:clarify:") for d in body["decisions"])
    assert body["dispatched_to"] == "compliance"
    assert body["state"]["status"] == "answered"


def test_concierge_echoes_merged_state_without_clobbering(api):
    state = {**_EMPTY_STATE, "slots": {"priority": "speed"}}
    r = _chat(api, "ship from Atlanta to Seattle weighing 10 lb", state)
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    slots = r.json()["state"]["slots"]
    assert slots.get("destination")             # extracted from the message
    assert slots.get("priority") == "speed"      # prior (form) slot preserved
