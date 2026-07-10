"""Trend alerts over the eval history (evals §11 — observability).

history.jsonl is the system of record; this turns it into the three alerts the
IR runbooks page/warn on:

* **page** — a blocking suite's gate FAILED in the latest run.
* **warn** — a suite's pass rate dropped more than ``drop_threshold`` against its
  trailing mean over the last ``window`` runs of the same lane (regression drift
  that hasn't tripped the gate yet).
* **warn** — the suite's judge_error rate exceeded ``judge_error_rate_max``
  (a judge that cannot judge is itself an incident — §10).

Pure + keyless: operates on the parsed history records. Rendered into trend.md
by merge_reports and consumable by any external sink via telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass

DROP_THRESHOLD = 0.05
JUDGE_ERROR_RATE_MAX = 0.02
WINDOW = 5


@dataclass(frozen=True)
class Alert:
    severity: str  # "page" | "warn"
    lane: str
    suite: str
    message: str

    def render(self) -> str:
        return f"**{self.severity.upper()}** [{self.lane}/{self.suite}] {self.message}"


def evaluate_history(
    records: list[dict],
    *,
    drop_threshold: float = DROP_THRESHOLD,
    judge_error_rate_max: float = JUDGE_ERROR_RATE_MAX,
    window: int = WINDOW,
) -> list[Alert]:
    """Alerts for the LATEST run, judged against its own lane's trailing history."""
    if not records:
        return []
    latest = records[-1]
    lane = latest.get("lane", "")
    prior = [r for r in records[:-1] if r.get("lane") == lane][-window:]

    alerts: list[Alert] = []
    for s in latest.get("suites", []):
        suite, n = s.get("suite", "?"), int(s.get("n", 0))

        if not s.get("gate_passed", True):
            alerts.append(Alert("page", lane, suite, f"gate FAILED: {s.get('gate', '')}"))

        rate = float(s.get("rate", 0.0))
        prior_rates = [
            float(ps["rate"])
            for r in prior
            for ps in r.get("suites", [])
            if ps.get("suite") == suite and "rate" in ps
        ]
        if prior_rates:
            baseline = sum(prior_rates) / len(prior_rates)
            drop = baseline - rate
            if drop > drop_threshold:
                alerts.append(
                    Alert(
                        "warn",
                        lane,
                        suite,
                        f"pass rate {rate:.0%} dropped {drop:.0%} below the "
                        f"{baseline:.0%} trailing mean ({len(prior_rates)} prior run(s))",
                    )
                )

        judge_errors = int(s.get("judge_errors", 0))
        if n and judge_errors / n > judge_error_rate_max:
            alerts.append(
                Alert(
                    "warn",
                    lane,
                    suite,
                    f"judge_error rate {judge_errors}/{n} exceeds "
                    f"{judge_error_rate_max:.0%} (§10 — judge itself is failing)",
                )
            )

    alerts.sort(key=lambda a: (a.severity != "page", a.suite))
    return alerts
