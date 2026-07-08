"""Statistical rigor & flakiness policy (evals guide §3.3, Gap A).

Stochastic LLM outputs make naive 85/95/98% gates on n=30-80 datasets a
coin-flip. This module encodes the determinism ladder's gate math so every
report is honest about noise:

- Percentage gates apply only when n >= 30; below that a suite gates on
  ZERO critical failures (not a rate).
- Safety-critical cases aggregate pass-all-of-N; quality cases majority-of-N.
- Pass rates are reported with a Wilson 95% interval so "94.8% vs 95%" reads
  as noise, not a regression.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_N_FOR_PERCENTAGE_GATE = 30


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for a pass rate (default 95%)."""
    if n == 0:
        return (0.0, 0.0)
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    margin = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def aggregate_verdict(verdicts: list[str], safety_critical: bool) -> str:
    """Collapse N repeated runs of one case into a single verdict.

    Safety-critical: pass-all-of-N (any fail => fail). Quality: majority-of-N.
    """
    if not verdicts:
        return "fail"
    passes = sum(1 for v in verdicts if v == "pass")
    if safety_critical:
        return "pass" if passes == len(verdicts) else "fail"
    return "pass" if passes * 2 > len(verdicts) else "fail"


def is_flaky(verdicts: list[str]) -> bool:
    """A case whose verdict flips across identical runs is flaky (=> monitor_only)."""
    return len(set(verdicts)) > 1


@dataclass
class GateResult:
    passed: bool
    n: int
    pass_count: int
    pass_rate: float
    wilson_low: float
    wilson_high: float
    mode: str  # "zero-critical-failure" | "percentage"
    detail: str


def gate(
    pass_count: int,
    n: int,
    *,
    critical_failures: int,
    min_pass_rate: float | None,
    lane: str,
) -> GateResult:
    """Decide whether a suite passes its gate for a lane.

    ``min_pass_rate`` is only honoured when n >= 30; below that the suite gates
    on zero critical failures. ``lane == "ci"`` always requires zero failures.
    """
    rate = pass_count / n if n else 0.0
    lo, hi = wilson_interval(pass_count, n)

    if lane == "ci" or n < MIN_N_FOR_PERCENTAGE_GATE or min_pass_rate is None:
        passed = critical_failures == 0 and (lane != "ci" or pass_count == n)
        mode = "zero-critical-failure"
        detail = (
            f"{mode}: {pass_count}/{n} pass, {critical_failures} critical failure(s)"
            + ("" if n >= MIN_N_FOR_PERCENTAGE_GATE else f" (n<{MIN_N_FOR_PERCENTAGE_GATE})")
        )
        return GateResult(passed, n, pass_count, rate, lo, hi, mode, detail)

    passed = critical_failures == 0 and hi >= min_pass_rate
    mode = "percentage"
    detail = f"{mode}: {rate:.1%} [{lo:.1%}-{hi:.1%}] vs >= {min_pass_rate:.0%}"
    return GateResult(passed, n, pass_count, rate, lo, hi, mode, detail)
