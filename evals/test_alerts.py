"""Trend alerts + telemetry sink tests (evals §11 — F9). Keyless."""

from __future__ import annotations

from evals import telemetry
from evals.alerts import evaluate_history
from evals.runners import run_lane


def _record(
    lane: str, *, rate: float, n: int = 30, gate_passed: bool = True, judge_errors: int = 0
):
    p = round(rate * n)
    return {
        "run_id": f"r-{lane}-{rate}",
        "lane": lane,
        "overall_pass": gate_passed,
        "suites": [
            {
                "suite": "safety/redteam",
                "layer": 4,
                "n": n,
                "pass": p,
                "rate": rate,
                "critical_failures": 0 if gate_passed else 1,
                "judge_errors": judge_errors,
                "gate_passed": gate_passed,
                "gate": "zero-critical-failure: detail",
                "flaky": [],
            }
        ],
    }


# ── alert math ────────────────────────────────────────────────────────────────
def test_healthy_history_produces_no_alerts():
    records = [_record("ci", rate=1.0) for _ in range(4)]
    assert evaluate_history(records) == []


def test_gate_failure_pages():
    records = [_record("ci", rate=1.0), _record("ci", rate=1.0, gate_passed=False)]
    alerts = evaluate_history(records)
    assert [a.severity for a in alerts] == ["page"]
    assert "gate FAILED" in alerts[0].message and alerts[0].suite == "safety/redteam"


def test_gate_failure_with_drop_pages_first():
    # Both signals fire; the page must outrank the drift warn.
    records = [_record("ci", rate=1.0), _record("ci", rate=0.8, gate_passed=False)]
    severities = [a.severity for a in evaluate_history(records)]
    assert severities == ["page", "warn"]


def test_pass_rate_drop_warns_against_trailing_mean():
    records = [_record("nightly", rate=1.0) for _ in range(3)] + [_record("nightly", rate=0.80)]
    alerts = evaluate_history(records)
    assert len(alerts) == 1 and alerts[0].severity == "warn"
    assert "dropped" in alerts[0].message


def test_small_dip_does_not_warn():
    records = [_record("nightly", rate=1.0), _record("nightly", rate=0.97)]
    assert evaluate_history(records) == []


def test_judge_error_rate_warns():
    records = [_record("nightly", rate=1.0, judge_errors=3)]  # 3/30 = 10% > 2%
    alerts = evaluate_history(records)
    assert len(alerts) == 1 and "judge_error" in alerts[0].message


def test_lanes_do_not_cross_contaminate():
    # A perfect CI history must not mask a nightly drop (baselines are per-lane).
    records = (
        [_record("ci", rate=1.0) for _ in range(5)]
        + [_record("nightly", rate=1.0)]
        + [_record("ci", rate=1.0)]
        + [_record("nightly", rate=0.5)]
    )
    alerts = evaluate_history(records)
    assert len(alerts) == 1 and alerts[0].lane == "nightly"


def test_empty_history_is_quiet():
    assert evaluate_history([]) == []


# ── judge_errors flows into the lane record ───────────────────────────────────
def test_lane_record_carries_judge_errors():
    record = run_lane.run_lane("ci", write=False)
    assert all("judge_errors" in s for s in record["suites"])
    assert all(s["judge_errors"] == 0 for s in record["suites"])  # keyless CI: judge never ran


# ── telemetry sink (§11, optional) ────────────────────────────────────────────
def test_telemetry_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv(telemetry.ENV_VAR, raising=False)
    sent: list = []
    assert telemetry.emit({"x": 1}, transport=lambda u, p: sent.append((u, p))) is False
    assert sent == []


def test_telemetry_posts_when_configured(monkeypatch):
    monkeypatch.setenv(telemetry.ENV_VAR, "https://sink.example/evals")
    sent: list = []
    assert telemetry.emit({"x": 1}, transport=lambda u, p: sent.append((u, p))) is True
    assert sent[0][0] == "https://sink.example/evals" and b'"x": 1' in sent[0][1]


def test_telemetry_swallows_transport_failure(monkeypatch):
    monkeypatch.setenv(telemetry.ENV_VAR, "https://sink.example/evals")

    def boom(url: str, payload: bytes) -> None:
        raise OSError("connection refused")

    assert telemetry.emit({"x": 1}, transport=boom) is False  # warned, not raised
