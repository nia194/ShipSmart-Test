"""Run a whole lane (ci | nightly | release): gate, trace, append history, trend.

    uv run python -m evals.runners.run_lane ci

Exits non-zero when a blocking lane (ci, release) has a failing gate, so CI
blocks. Nightly never blocks (alerts on trend deltas via merge_reports).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from ..case_model import load_jsonl
from ..graders import llm_judge
from ..manifest import load_manifest, verify
from ..protocol import EchoSUT, SystemUnderTest
from ..telemetry import emit as emit_telemetry
from .merge_reports import regenerate_trend
from .run_suite import LANE_CONFIG, run_suite

EVALS_DIR = Path(__file__).resolve().parents[1]
REPORTS_DIR = EVALS_DIR / "reports"
HISTORY = REPORTS_DIR / "history.jsonl"

# Per-suite system-under-test. F0 ships the deterministic keyless EchoSUT for
# every suite; later phases register real SUTs (live API, scripted agent, ...).
SUT_REGISTRY: dict[str, SystemUnderTest] = {}


def _sut_for(suite: str) -> SystemUnderTest:
    return SUT_REGISTRY.get(suite, EchoSUT())


def _repo_shas() -> dict[str, str]:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=EVALS_DIR, text=True, stderr=subprocess.DEVNULL
        ).strip()
        return {"ShipSmart-Test": sha}
    except Exception:  # pragma: no cover - git optional
        return {}


def run_lane(lane: str, *, write: bool = True) -> dict:
    if lane not in LANE_CONFIG:
        raise SystemExit(f"unknown lane {lane!r} (expected one of {sorted(LANE_CONFIG)})")
    run_id = f"{int(time.time())}-{lane}"
    shas = _repo_shas()
    entries = load_manifest()
    # The judge runs only where the lane allows model graders AND a provider key
    # exists — so CI (and any keyless run) stays deterministic and free.
    judge_on = bool(LANE_CONFIG[lane]["model_graders"] and llm_judge.available())

    suite_summaries: list[dict] = []
    all_traces = []
    overall_pass = True
    for entry in entries:
        verify(entry)
        cases = load_jsonl(entry.path)
        result = run_suite(
            entry,
            cases,
            _sut_for(entry.suite),
            lane=lane,
            run_id=run_id,
            repo_shas=shas,
            has_judge_client=judge_on,
        )
        all_traces.extend(result.traces)
        overall_pass = overall_pass and result.gate.passed
        suite_summaries.append(
            {
                "suite": result.suite,
                "layer": result.layer,
                "dataset_version": result.dataset_version,
                "n": result.n_cases,
                "pass": result.pass_count,
                "rate": round(result.gate.pass_rate, 4),
                "wilson": [round(result.gate.wilson_low, 4), round(result.gate.wilson_high, 4)],
                "critical_failures": result.critical_failures,
                "judge_errors": result.judge_errors,
                "gate_passed": result.gate.passed,
                "gate": result.gate.detail,
                "flaky": result.flaky_cases,
            }
        )

    record = {
        "run_id": run_id,
        "at": datetime.now(UTC).isoformat(),
        "lane": lane,
        "repo_shas": shas,
        "overall_pass": overall_pass,
        "suites": suite_summaries,
        "total_cases": sum(s["n"] for s in suite_summaries),
        "total_pass": sum(s["pass"] for s in suite_summaries),
    }

    if write:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with HISTORY.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True) + "\n")
        traces_path = REPORTS_DIR / "traces" / f"{run_id}.jsonl"
        traces_path.parent.mkdir(parents=True, exist_ok=True)
        traces_path.write_text("\n".join(t.to_json_line() for t in all_traces), encoding="utf-8")
        regenerate_trend()
        emit_telemetry(record)  # no-op unless EVAL_TELEMETRY_SINK is set (§11)

    return record


def _print(record: dict) -> None:
    print(f"== eval lane: {record['lane']}  run {record['run_id']} ==")
    for s in record["suites"]:
        mark = "PASS" if s["gate_passed"] else "FAIL"
        print(f"  [{mark}] L{s['layer']} {s['suite']} ({s['dataset_version']}): {s['gate']}"
              + (f"  flaky={s['flaky']}" if s["flaky"] else ""))
    print(f"-- overall: {'PASS' if record['overall_pass'] else 'FAIL'} "
          f"({record['total_pass']}/{record['total_cases']} cases)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run a ShipSmart eval lane.")
    ap.add_argument("lane", choices=sorted(LANE_CONFIG))
    ap.add_argument("--no-write", action="store_true", help="don't append history/traces")
    args = ap.parse_args(argv)
    record = run_lane(args.lane, write=not args.no_write)
    _print(record)
    blocking = LANE_CONFIG[args.lane]["blocking"]
    return 0 if (record["overall_pass"] or not blocking) else 1


if __name__ == "__main__":
    sys.exit(main())
