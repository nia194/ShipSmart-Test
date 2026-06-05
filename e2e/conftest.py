"""
Fixtures for the live e2e tests.

The stack is hosted out-of-band by ``scripts/run-stack.sh up`` (or docker-compose).
These fixtures only connect + health-check; a service that's down makes its tests
SKIP (never fail), so MCP+API still run even if the optional Java service is off.
"""

from __future__ import annotations

import os
import time

import httpx
import jwt as pyjwt
import pytest

MCP_URL = os.getenv("SHIPSMART_E2E_MCP_URL", "http://127.0.0.1:8001")
API_URL = os.getenv("SHIPSMART_E2E_API_URL", "http://127.0.0.1:8000")
JAVA_URL = os.getenv("SHIPSMART_E2E_JAVA_URL", "http://127.0.0.1:8080")
JWT_SECRET = os.getenv("SHIPSMART_E2E_JWT_SECRET", "e2e-test-secret-please-change-32chars-minimum")


def _healthy(base: str, path: str) -> bool:
    try:
        return httpx.get(base + path, timeout=2.0).status_code == 200
    except Exception:
        return False


def mint_jwt(sub: str, hours: int = 1) -> str:
    """Mint an HS256 token the Java SupabaseJwtVerifier accepts (sub = user id)."""
    now = int(time.time())
    return pyjwt.encode(
        {"sub": sub, "iat": now, "exp": now + hours * 3600, "role": "authenticated"},
        JWT_SECRET, algorithm="HS256",
    )


@pytest.fixture
def jwt_for():
    """Return a minting function: jwt_for(user_id) -> bearer token string."""
    return mint_jwt


@pytest.fixture(scope="session")
def mcp():
    if not _healthy(MCP_URL, "/health"):
        pytest.skip("MCP not running — start it with scripts/run-stack.sh up")
    with httpx.Client(base_url=MCP_URL, timeout=15.0) as c:
        yield c


@pytest.fixture(scope="session")
def api():
    if not _healthy(API_URL, "/health"):
        pytest.skip("API not running — start it with scripts/run-stack.sh up")
    with httpx.Client(base_url=API_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def java():
    if not _healthy(JAVA_URL, "/api/v1/health"):
        pytest.skip("Java not running (optional service)")
    with httpx.Client(base_url=JAVA_URL, timeout=20.0) as c:
        yield c
