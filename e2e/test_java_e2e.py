"""Live e2e against ShipSmart-Orchestrator (optional service).

Proves the read endpoints are real, JWT-scoped, and ownership-safe against a real
Postgres — the same behavior the (skipped-without-Docker) Testcontainers IT covers,
exercised end-to-end over HTTP.
"""

from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.e2e

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_shipments_requires_auth(java):
    assert java.get("/api/v1/shipments").status_code == 401


def test_unknown_shipment_is_404(java, jwt_for):
    r = java.get(f"/api/v1/shipments/{uuid.uuid4()}", headers=_auth(jwt_for(USER_A)))
    assert r.status_code == 404


def test_create_read_list_and_ownership_scoping(java, jwt_for):
    a = jwt_for(USER_A)
    body = {
        "origin": "10001", "destination": "90210",
        "dropOffDate": "2026-06-01", "expectedDeliveryDate": "2026-06-07",
        "packages": [], "totalWeight": 10.0, "totalItems": 1,
    }
    created = java.post(
        "/api/v1/shipments",
        headers={**_auth(a), "Idempotency-Key": str(uuid.uuid4())},
        json=body,
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]

    # owner can read it
    assert java.get(f"/api/v1/shipments/{sid}", headers=_auth(a)).status_code == 200
    # it appears in the owner's list
    listing = java.get("/api/v1/shipments", headers=_auth(a)).json()
    assert any(s["id"] == sid for s in listing["content"])
    # a different JWT user cannot read it (ownership not bypassable via the URL)
    b = jwt_for(USER_B)
    assert java.get(f"/api/v1/shipments/{sid}", headers=_auth(b)).status_code == 404
