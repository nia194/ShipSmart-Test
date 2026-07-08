"""LLM-as-judge standard (evals guide §10).

One implementation: load a rubric, call the pinned judge (configurable — default
OpenAI gpt-4o, Anthropic Claude supported) through the API's ``LLMRouter`` in
structured/tool mode, return the structured verdict contract below. The judge
runs only in nightly/release, never in CI, and never decides Layer-4 safety.
Invalid JSON -> one corrective retry -> ``judge_error`` (never a silent pass).
Pinning + versioning live in ``config/judge.yml``; a rubric edit is a version
bump so historical trends stay valid.

F0 ships the config loader + the verdict contract; wiring the judge client to a
live provider is done in the judge phase (only smoke cases with no ``judge_rubric``
run in F0, so this is never invoked keyless).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

from ..case_model import Case
from ..protocol import Response
from . import Verdict

JUDGE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "judge.yml"


@dataclass(frozen=True)
class JudgeConfig:
    provider: str
    model: str
    temperature: float
    rubric_versions: dict[str, str]
    fallback: list[dict]

    @property
    def judge_version(self) -> str:
        rv = ",".join(f"{k}={v}" for k, v in sorted(self.rubric_versions.items()))
        return f"{self.provider}/{self.model}@[{rv}]"


@lru_cache(maxsize=1)
def load_judge_config(path: str | Path = JUDGE_CONFIG_PATH) -> JudgeConfig:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    j = doc.get("judge", {})
    return JudgeConfig(
        provider=j.get("provider", "openai"),
        model=j.get("model", "gpt-4o"),
        temperature=float(j.get("temperature", 0.0)),
        rubric_versions=dict(j.get("rubric_versions", {})),
        fallback=list(j.get("fallback", [])),
    )


# Structured verdict contract (CI-stable, parse-validated) — evals §10.
VERDICT_SCHEMA_KEYS = {"score", "verdict", "reasoning", "violations"}


def parse_verdict(obj: dict) -> Verdict:
    if not VERDICT_SCHEMA_KEYS.issubset(obj):
        raise ValueError(f"judge_error: verdict missing keys {VERDICT_SCHEMA_KEYS - set(obj)}")
    return Verdict(
        passed=obj["verdict"] == "pass",
        grader="llm_judge",
        reason=str(obj.get("reasoning", ""))[:400],
        score=float(obj["score"]),
    )


def grade(case: Case, resp: Response, *, judge_client=None) -> Verdict:  # pragma: no cover
    """Grade a case's declared ``judge_rubric``. Requires a configured judge client."""
    if judge_client is None:
        raise NotImplementedError(
            "llm_judge requires a configured judge client (nightly/release + keys); "
            "F0 runs no cases with a judge_rubric"
        )
    cfg = load_judge_config()
    raw = judge_client.judge(
        rubric=case.expected.judge_rubric,
        response=resp.text,
        provider=cfg.provider,
        model=cfg.model,
    )
    return parse_verdict(raw)
