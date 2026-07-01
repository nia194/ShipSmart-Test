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
    # Form-provided slots satisfy the requirement, so the turn dispatches (no re-ask).
    # The exact worker depends on deployment flags: the UC2 compliance pass, or — when
    # this international shipment also has the multi-agent workflow enabled (run-stack's
    # default) — the full workflow bridge.
    assert body["dispatched_to"] in ("compliance", "workflow")
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


def test_concierge_persists_and_recalls_by_session(api):
    """A turn is persisted server-side; GET /concierge/{id} replays it (reload recall)."""
    r = _chat(api, "ship from Atlanta to Seattle weighing 10 lb")
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert sid

    h = api.get(f"/api/v1/concierge/{sid}")
    assert h.status_code == 200, h.text
    body = h.json()
    assert body["session_id"] == sid
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["state"]["slots"].get("destination")  # merged state recalled


def test_concierge_greets_and_orients(api):
    """A pure greeting is welcomed + oriented, not dispatched to the RAG agent."""
    r = _chat(api, "hi")
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "concierge:greeting" in body["decisions"]
    assert body["dispatched_to"] is None
    assert body["reply"].startswith("Hi!")


def test_concierge_parses_lowercase_city_route(api):
    """Lowercase city names resolve to a route + countries (were silently dropped)."""
    r = _chat(api, "atlanta to seattle, 12 lb")
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    slots = r.json()["state"]["slots"]
    assert slots.get("origin") and slots.get("destination")
    assert slots.get("origin_country") == "US" and slots.get("destination_country") == "US"
    assert slots.get("weight_lbs") == 12.0


def test_concierge_natural_quote_gathers_then_dispatches(api):
    """"send a gift" is a shipping intent → gather route + weight, then dispatch.
    Keyless the final turn is a deterministic summary; the point is it no longer
    dead-ends on "I don't have enough information"."""
    r = _chat(api, "I need to send a gift to my mom")
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"]["intent"] == "quote"
    assert body["dispatched_to"] is None  # gathering, not dumped to the advice agent

    body = _chat(api, "from chicago to denver", body["state"]).json()
    body = _chat(api, "about 5 pounds", body["state"]).json()
    assert body["dispatched_to"] in ("summary", "agent")  # completed, not a refusal
    assert body["state"]["slots"].get("weight_lbs") == 5.0


def test_concierge_bridges_to_workflow_for_international(api):
    """worldwide + compliance + workflow ON ⇒ an international shipment drives the
    full multi-agent workflow (run-stack enables all three)."""
    state = {
        **_EMPTY_STATE,
        "slots": {"destination_country": "BR", "description": "drone with lithium battery"},
        "intent": "compliance",
    }
    r = _chat(api, "is my drone with a lithium battery allowed to Brazil?", state)
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    assert r.status_code == 200, r.text
    body = r.json()
    if body["dispatched_to"] != "workflow":
        pytest.skip("workflow bridge off (needs SHIPPING_SCOPE=worldwide + WORKFLOW_ENABLED=true)")
    assert any(d.startswith("workflow:") for d in body["decisions"])


def test_concierge_workflow_bridge_runs_to_terminal_state(api):
    """The bridge drives the multi-agent workflow to a terminal outcome via the concierge
    entry: it COMPLETES, or SUSPENDS for human review when a high-risk area can't be
    verified (which it is/isn't depends on RAG corpus coverage — both are valid)."""
    state = {
        **_EMPTY_STATE,
        "slots": {"destination_country": "BR", "description": "drone with a lithium battery"},
        "intent": "compliance",
    }
    r = _chat(api, "is my drone with a lithium battery allowed to Brazil?", state)
    if r.status_code == 404:
        pytest.skip("concierge disabled — set CONCIERGE_ENABLED=true")
    body = r.json()
    if body["dispatched_to"] != "workflow":
        pytest.skip("workflow bridge off (needs worldwide + compliance + workflow)")
    decisions = body["decisions"]
    assert "workflow:start" in decisions
    assert ("workflow:complete" in decisions) or (
        "workflow:interrupt:human_review" in decisions
    ), decisions
    # when it does suspend, the reply must guide the user to review
    if "workflow:interrupt:human_review" in decisions:
        assert "review" in body["reply"].lower()
