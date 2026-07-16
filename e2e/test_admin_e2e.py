"""Live e2e for the runtime AI-controls admin surface (Governance §12).

Fail-closed by design: with no ADMIN_API_TOKEN configured the endpoint 404s —
run-stack.sh configures the non-secret e2e token, so a 404 means an older
stack: skip rather than fail.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.e2e

# Mirrors conftest.py / run-stack.sh (e2e/ is not a package, so no relative import).
ADMIN_TOKEN = os.getenv("SHIPSMART_E2E_ADMIN_TOKEN", "e2e-admin-token-nonsecret")

KILLABLE = {"agent", "concierge", "workflow", "compliance", "rag"}


def _get_controls(api):
    r = api.get("/api/v1/admin/ai-controls", headers={"X-Admin-Token": ADMIN_TOKEN})
    if r.status_code == 404:
        pytest.skip("admin surface unconfigured (ADMIN_API_TOKEN unset)")
    assert r.status_code == 200, r.text
    return r.json()["features"]


def test_ai_controls_snapshot_lists_every_killable_feature(api):
    features = _get_controls(api)
    assert set(features) == KILLABLE
    assert all(isinstance(v, bool) for v in features.values())


def test_ai_controls_rejects_wrong_token(api):
    _get_controls(api)  # skip when the surface is unconfigured (404 either way)
    r = api.get("/api/v1/admin/ai-controls", headers={"X-Admin-Token": "wrong-token"})
    assert r.status_code == 403


def test_ai_controls_flip_is_applied_and_restored(api):
    """Kill one feature at runtime, see the snapshot change, then restore it."""
    features = _get_controls(api)
    assert features["compliance"] is True, "expected compliance live before the flip"
    headers = {"X-Admin-Token": ADMIN_TOKEN}
    try:
        r = api.post("/api/v1/admin/ai-controls", headers=headers,
                     json={"feature": "compliance", "enabled": False, "reason": "e2e drill"})
        assert r.status_code == 200, r.text
        assert r.json()["features"]["compliance"] is False
    finally:
        r = api.post("/api/v1/admin/ai-controls", headers=headers,
                     json={"feature": "compliance", "enabled": True, "reason": "e2e restore"})
        assert r.status_code == 200, r.text
    assert _get_controls(api)["compliance"] is True


def test_ai_controls_unknown_feature_rejected(api):
    _get_controls(api)
    r = api.post("/api/v1/admin/ai-controls", headers={"X-Admin-Token": ADMIN_TOKEN},
                 json={"feature": "not-a-feature", "enabled": False})
    assert r.status_code == 422
