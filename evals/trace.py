"""The EvalTrace envelope (evals guide §3.4) — one JSONL line per run.

Mirrors the guardrails ``AIEvent`` correlation keys (request/decisions/tools/
sources/provider/cost) so online sampling (production AIEvent) maps cleanly onto
an eval run (EvalTrace).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass
class EvalTrace:
    run_id: str
    lane: str  # ci | nightly | release
    case_id: str
    dataset_version: str
    repo_shas: dict[str, str] = field(default_factory=dict)
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    judge_version: str | None = None
    run_index: int = 0
    verdict: str = "pass"  # pass | fail
    score: float | None = None
    decisions: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    tokens: int = 0
    cost_usd: float = 0.0
    reason: str = ""

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)
