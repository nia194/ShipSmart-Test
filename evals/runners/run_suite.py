"""Run one suite's cases through a system-under-test + graders for a lane."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..case_model import Case
from ..graders import Verdict, llm_judge, rule_based, semantic
from ..manifest import SuiteEntry
from ..protocol import Response, SystemUnderTest
from ..rigor import GateResult, aggregate_verdict, gate, is_flaky
from ..trace import EvalTrace

# Per-lane behaviour (evals guide §3.4).
LANE_CONFIG = {
    "ci": {"repetition": 1, "splits": {"dev"}, "model_graders": False, "blocking": True},
    "nightly": {"repetition": 3, "splits": {"dev"}, "model_graders": True, "blocking": False},
    "release": {
        "repetition": 5,
        "splits": {"dev", "holdout"},
        "model_graders": True,
        "blocking": True,
    },
}


@dataclass
class SuiteResult:
    suite: str
    layer: int
    dataset_version: str
    n_cases: int
    pass_count: int
    critical_failures: int
    gate: GateResult
    flaky_cases: list[str] = field(default_factory=list)
    traces: list[EvalTrace] = field(default_factory=list)


def _grade_once(case: Case, resp: Response, lane: str, has_judge_client: bool) -> Verdict:
    v = rule_based.grade(case, resp)
    if not v.passed:
        return v
    model_graders = LANE_CONFIG[lane]["model_graders"]
    if model_graders and case.expected.relevant_doc_ids:
        v = semantic.grade(case, resp)
        if not v.passed:
            return v
    if model_graders and case.expected.judge_rubric and has_judge_client:
        v = llm_judge.grade(case, resp)  # pragma: no cover - needs keys
    return v


def run_suite(
    entry: SuiteEntry,
    cases: list[Case],
    sut: SystemUnderTest,
    *,
    lane: str,
    run_id: str,
    repo_shas: dict[str, str] | None = None,
    min_pass_rate: float | None = None,
    has_judge_client: bool = False,
) -> SuiteResult:
    cfg = LANE_CONFIG[lane]
    splits: set[str] = cfg["splits"]
    reps: int = cfg["repetition"]
    scoped = [c for c in cases if c.split in splits]

    pass_count = 0
    critical_failures = 0
    flaky: list[str] = []
    traces: list[EvalTrace] = []

    for case in scoped:
        n = max(reps, case.runs) if lane != "ci" else 1
        verdicts: list[str] = []
        for i in range(n):
            t0 = time.perf_counter()
            resp = sut(case)
            v = _grade_once(case, resp, lane, has_judge_client)
            latency = (time.perf_counter() - t0) * 1000
            verdicts.append(v.verdict)
            traces.append(
                EvalTrace(
                    run_id=run_id,
                    lane=lane,
                    case_id=case.id,
                    dataset_version=entry.active_version,
                    repo_shas=dict(repo_shas or {}),
                    provider=resp.provider,
                    model=resp.model,
                    judge_version=(
                        llm_judge.load_judge_config().judge_version if has_judge_client else None
                    ),
                    run_index=i,
                    verdict=v.verdict,
                    score=v.score,
                    decisions=list(resp.decisions),
                    sources=list(resp.sources),
                    tool_calls=list(resp.tool_calls),
                    latency_ms=latency,
                    tokens=resp.tokens,
                    cost_usd=resp.cost_usd,
                    reason=v.reason,
                )
            )
        agg = aggregate_verdict(verdicts, case.is_safety_critical)
        if is_flaky(verdicts):
            flaky.append(case.id)
        if agg == "pass":
            pass_count += 1
        elif case.severity == "critical":
            critical_failures += 1

    g = gate(
        pass_count,
        len(scoped),
        critical_failures=critical_failures,
        min_pass_rate=min_pass_rate,
        lane=lane,
    )
    return SuiteResult(
        suite=entry.suite,
        layer=entry.layer,
        dataset_version=entry.active_version,
        n_cases=len(scoped),
        pass_count=pass_count,
        critical_failures=critical_failures,
        gate=g,
        flaky_cases=flaky,
        traces=traces,
    )
