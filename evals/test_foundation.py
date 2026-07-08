"""Foundation (F0) smoke test — proves the eval harness runs end-to-end, keyless.

Exercises: tag vocabulary, manifest + sha256 integrity, case model, rigor gate
math, the rule-based grader on the EchoSUT, and all three lanes appending a
history record. No services, no keys.
"""

from __future__ import annotations

import pytest

from evals import manifest, rigor, tags
from evals.case_model import load_jsonl
from evals.graders import rule_based
from evals.protocol import EchoSUT
from evals.runners import run_lane


def test_tag_vocabulary_loads_and_has_guardrail_namespace():
    known = tags.known_tags()
    assert known, "tag vocabulary is empty"
    assert tags.guardrail_tags(), "no guardrail:* tags defined"
    assert "guardrail:injection" in known
    assert tags.unknown_tags(["agent:plan", "guardrail:misuse_refused"]) == set()
    assert tags.unknown_tags(["nope:invented"]) == {"nope:invented"}


def test_manifest_loads_and_sha256_has_not_drifted():
    entries = manifest.load_manifest()
    assert entries, "manifest has no suites"
    for entry in entries:
        manifest.verify(entry)  # raises on missing file or sha256 drift


def test_smoke_dataset_valid_and_tags_are_canonical():
    entry = next(e for e in manifest.load_manifest() if e.suite == "smoke/foundation")
    cases = load_jsonl(entry.path)
    assert len(cases) == entry.case_count
    known = tags.known_tags()
    for c in cases:
        for t in c.tags:
            assert t in known, f"{c.id}: undeclared tag {t!r} (decision-tag contract)"


def test_rule_based_grader_passes_echo_sut_on_smoke_cases():
    entry = next(e for e in manifest.load_manifest() if e.suite == "smoke/foundation")
    sut = EchoSUT()
    for case in load_jsonl(entry.path):
        v = rule_based.grade(case, sut(case))
        assert v.passed, f"{case.id}: {v.reason}"


def test_rigor_gate_math():
    lo, hi = rigor.wilson_interval(48, 50)
    assert 0 <= lo <= hi <= 1
    # safety-critical => pass-all-of-N; quality => majority-of-N
    assert rigor.aggregate_verdict(["pass", "pass", "fail"], safety_critical=True) == "fail"
    assert rigor.aggregate_verdict(["pass", "pass", "fail"], safety_critical=False) == "pass"
    assert rigor.is_flaky(["pass", "fail"]) is True
    # below n=30 => zero-critical-failure mode, not a percentage
    g = rigor.gate(5, 5, critical_failures=0, min_pass_rate=0.95, lane="ci")
    assert g.passed and g.mode == "zero-critical-failure"
    g2 = rigor.gate(5, 5, critical_failures=1, min_pass_rate=None, lane="release")
    assert not g2.passed


@pytest.mark.parametrize("lane", ["ci", "nightly", "release"])
def test_all_three_lanes_run_green_and_report(lane):
    record = run_lane.run_lane(lane, write=False)
    assert record["overall_pass"], record["suites"]
    assert record["total_cases"] >= 5
    assert record["lane"] == lane


def test_lane_writes_history_and_trend(tmp_path, monkeypatch):
    # Redirect the reports dir so the test doesn't touch the committed tree.
    monkeypatch.setattr(run_lane, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(run_lane, "HISTORY", tmp_path / "history.jsonl")
    from evals.runners import merge_reports

    monkeypatch.setattr(merge_reports, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(merge_reports, "HISTORY", tmp_path / "history.jsonl")
    monkeypatch.setattr(merge_reports, "TREND", tmp_path / "trend.md")
    run_lane.run_lane("ci", write=True)
    assert (tmp_path / "history.jsonl").exists()
    assert (tmp_path / "trend.md").exists()
