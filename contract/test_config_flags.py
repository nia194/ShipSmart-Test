"""Contract: ShipSmart-API feature flags are documented and gated (evals §4.2).

Every ``*_enabled`` Settings flag must (a) appear in ``.env.example`` so operators
can find it, and (b) be referenced by a test — a feature gate with no route-gating
test is how a 404-when-disabled promise silently rots.
"""

from __future__ import annotations

from sibling import API, api_settings_flags, api_test_blob, env_example_vars


def test_enabled_flags_documented_and_gated():
    flags = api_settings_flags()
    assert flags, "no *_enabled flags found on ShipSmart-API Settings"

    env_vars = env_example_vars(API)
    tests = api_test_blob()

    undocumented = sorted(f for f in flags if f.upper() not in env_vars)
    ungated = sorted(f for f in flags if f not in tests and f.upper() not in tests)

    assert not undocumented, f".env.example is missing *_enabled flags: {undocumented}"
    assert not ungated, f"*_enabled flags with no gating test: {ungated}"
