"""Judge/human calibration math (evals §10, §12).

The monthly calibration ritual: two humans (and the LLM judge) label the same
traces per rubric. We quantify agreement two ways — raw agreement and Cohen's
kappa (which corrects for agreement by chance) — and gate on it: below
``min_agreement`` the rubric is frozen (version-bumped) before its scores gate
anything. Pure + keyless, so the gate itself is deterministic and unit-tested.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


def raw_agreement(a: list[str], b: list[str]) -> float:
    """Fraction of items two raters labeled identically."""
    _check(a, b)
    if not a:
        return 1.0
    return sum(x == y for x, y in zip(a, b, strict=True)) / len(a)


def cohens_kappa(a: list[str], b: list[str]) -> float:
    """Cohen's kappa for two raters over a shared, ordered set of items.

    kappa = (po - pe) / (1 - pe); 1.0 perfect, 0.0 chance-level, <0 worse than
    chance. Returns 1.0 when both raters are unanimous and identical (pe == 1).
    """
    _check(a, b)
    n = len(a)
    if n == 0:
        return 1.0
    po = raw_agreement(a, b)
    ca, cb = Counter(a), Counter(b)
    labels = set(ca) | set(cb)
    pe = sum((ca.get(k, 0) / n) * (cb.get(k, 0) / n) for k in labels)
    if pe >= 1.0:  # both raters used a single identical label — perfect by definition
        return 1.0
    return (po - pe) / (1.0 - pe)


@dataclass(frozen=True)
class CalibrationResult:
    rubric: str
    n: int
    raw_agreement: float
    kappa: float
    min_agreement: float

    @property
    def passed(self) -> bool:
        """Gate on raw agreement (the §12 rule); kappa is reported alongside."""
        return self.raw_agreement >= self.min_agreement

    @property
    def verdict(self) -> str:
        return "ok" if self.passed else "FREEZE_RUBRIC"


def calibrate(
    rubric: str, rater_a: list[str], rater_b: list[str], min_agreement: float = 0.80
) -> CalibrationResult:
    return CalibrationResult(
        rubric=rubric,
        n=len(rater_a),
        raw_agreement=raw_agreement(rater_a, rater_b),
        kappa=cohens_kappa(rater_a, rater_b),
        min_agreement=min_agreement,
    )


def _check(a: list[str], b: list[str]) -> None:
    if len(a) != len(b):
        raise ValueError(f"rater label counts differ: {len(a)} vs {len(b)}")
