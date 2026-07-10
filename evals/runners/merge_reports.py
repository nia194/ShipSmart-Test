"""Regenerate reports/trend.md from reports/history.jsonl (evals guide §11).

The flat append-only history is the system of record; trend.md is the
human-readable last-30-runs table with pass-rate deltas. Keyless, offline.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..alerts import evaluate_history

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"
HISTORY = REPORTS_DIR / "history.jsonl"
TREND = REPORTS_DIR / "trend.md"
WINDOW = 30


def _load_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def regenerate_trend() -> str:
    records = _load_history()[-WINDOW:]
    lines = [
        "# ShipSmart evals — trend",
        "",
        f"Last {len(records)} run(s) from `history.jsonl` (append-only system of record).",
        "",
        "| run_id | when | lane | overall | cases | suites (rate Δ) |",
        "|---|---|---|---|---|---|",
    ]
    prev_rates: dict[str, float] = {}
    for rec in records:
        parts = []
        for s in rec.get("suites", []):
            rate = s.get("rate", 0.0)
            delta = rate - prev_rates.get(s["suite"], rate)
            arrow = "→" if abs(delta) < 1e-9 else ("↑" if delta > 0 else "↓")
            parts.append(f"{s['suite']} {rate:.0%}{arrow}")
            prev_rates[s["suite"]] = rate
        overall = "✅" if rec.get("overall_pass") else "❌"
        lines.append(
            f"| `{rec['run_id']}` | {rec.get('at', '')[:19]} | {rec['lane']} | {overall} "
            f"| {rec.get('total_pass', 0)}/{rec.get('total_cases', 0)} | {'; '.join(parts)} |"
        )
    if not records:
        lines.append("| _(no runs yet)_ | | | | | |")

    # §11 alerts for the latest run (page = gate fail; warn = drift / judge_error).
    alerts = evaluate_history(records)
    lines += ["", "## Alerts (latest run)", ""]
    lines += [f"- {a.render()}" for a in alerts] or ["_none_"]

    content = "\n".join(lines) + "\n"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    TREND.write_text(content, encoding="utf-8")
    return content


if __name__ == "__main__":
    print(regenerate_trend())
