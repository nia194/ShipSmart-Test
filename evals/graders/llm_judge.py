"""LLM-as-judge standard (evals guide §10).

Load a per-case rubric, call the pinned judge (configurable — default OpenAI
gpt-4o, Anthropic Claude supported as failover), and return the structured verdict
contract below. The judge runs ONLY in nightly/release, never in CI (keys, cost,
variance), and NEVER decides a Layer-4 safety verdict — rule-based owns safety.
Invalid JSON → one corrective retry → ``judge_error`` (counted, never a silent
pass). Pinning + rubric versions live in ``config/judge.yml``; a rubric edit is a
version bump so historical ``judge_version``-stamped trends stay valid.

The prompt construction + verdict parsing + retry state machine are pure and
unit-tested with a fake client; the provider HTTP calls run only with real keys.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import yaml

from ..case_model import Case
from ..protocol import Response
from . import Verdict

EVALS_DIR = Path(__file__).resolve().parents[1]
JUDGE_CONFIG_PATH = EVALS_DIR / "config" / "judge.yml"
RUBRIC_DIR = Path(__file__).resolve().parent / "judge_prompts"

# Provider key env vars — presence gates whether the judge can run at all.
PROVIDER_KEYS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


@dataclass(frozen=True)
class JudgeConfig:
    provider: str
    model: str
    temperature: float
    max_tokens: int
    seed: int
    max_retries: int
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
        max_tokens=int(j.get("max_tokens", 512)),
        seed=int(j.get("seed", 7)),
        max_retries=int(j.get("max_retries", 1)),
        rubric_versions=dict(j.get("rubric_versions", {})),
        fallback=list(j.get("fallback", [])),
    )


# ── Structured verdict contract (CI-stable, parse-validated) — evals §10 ───────
# score is a 1-5 quality scale (§10); verdict is the independent pass/fail.
VERDICT_SCHEMA_KEYS = {"score", "verdict", "reasoning", "violations"}
SCORE_MIN, SCORE_MAX = 1.0, 5.0
JUDGE_SCORE_ALERT_FLOOR = 4.0  # Layer-5 trend alert fires below this average (§11)
_CONTRACT_HINT = (
    'Return ONLY JSON: {"score": 1-5, "verdict": "pass"|"fail", '
    '"reasoning": "<=60 words, cite the specific claim/chunk", "violations": ["..."]}'
)
_CORRECTIVE = "\n\nYour previous reply was not valid JSON matching the contract. " + _CONTRACT_HINT
_SYSTEM = (
    "You are a strict, impartial evaluator of an AI shipping assistant's output. "
    "Judge ONLY against the rubric. You never make a safety determination. " + _CONTRACT_HINT
)


class JudgeError(Exception):
    """Transport/format failure that survives the corrective retry."""


class JudgeClient(Protocol):
    def judge(self, system: str, user: str, cfg: JudgeConfig) -> dict: ...


def build_user_prompt(rubric: str, response_text: str) -> str:
    return (
        f"Rubric:\n{rubric.strip()}\n\n"
        f'Assistant response to evaluate:\n"""\n{response_text.strip()}\n"""\n\n'
        f"{_CONTRACT_HINT}"
    )


def load_rubric(name: str) -> str:
    """Load a standard rubric template by name (version-pinned in judge.yml)."""
    return (RUBRIC_DIR / f"{name}.md").read_text(encoding="utf-8")


def parse_verdict(obj: dict) -> Verdict:
    if not VERDICT_SCHEMA_KEYS.issubset(obj):
        raise ValueError(f"judge_error: verdict missing keys {VERDICT_SCHEMA_KEYS - set(obj)}")
    score = float(obj["score"])
    if not SCORE_MIN <= score <= SCORE_MAX:
        raise ValueError(f"judge_error: score {score} out of [{SCORE_MIN},{SCORE_MAX}]")
    if obj["verdict"] not in {"pass", "fail"}:
        raise ValueError(f"judge_error: verdict {obj['verdict']!r} not pass/fail")
    return Verdict(
        passed=obj["verdict"] == "pass",
        grader="llm_judge",
        reason=str(obj.get("reasoning", ""))[:400],
        score=score,
    )


def _judge_error(reason: str) -> Verdict:
    # A judge that cannot judge does NOT pass the case — the failure is surfaced.
    return Verdict(passed=False, grader="llm_judge", reason=f"judge_error: {reason}", score=None)


def available(cfg: JudgeConfig | None = None) -> bool:
    """True only if the configured provider (or a fallback) has a key in the env."""
    cfg = cfg or load_judge_config()
    providers = [cfg.provider, *[f.get("provider") for f in cfg.fallback]]
    return any(os.environ.get(PROVIDER_KEYS.get(p or "", "")) for p in providers)


@lru_cache(maxsize=1)
def get_judge_client() -> JudgeClient | None:
    """The live provider client, or None when no key is configured (keyless lanes)."""
    if not available():
        return None
    return HttpJudgeClient()  # pragma: no cover - needs keys


def grade(case: Case, resp: Response, *, judge_client: JudgeClient | None = None) -> Verdict:
    """Grade a case's declared ``judge_rubric``. Resolves a live client if none given."""
    # Hard invariant: the judge never decides Layer-4 safety.
    if case.layer == 4:
        return _judge_error("refused to grade Layer-4 safety (rule-based owns safety)")
    rubric = case.expected.judge_rubric
    if not rubric:
        return _judge_error("no judge_rubric on case")

    client = judge_client or get_judge_client()
    if client is None:
        return _judge_error("no judge client configured")

    cfg = load_judge_config()
    system, base_user = _SYSTEM, build_user_prompt(rubric, resp.text)
    last = ""
    for attempt in range(cfg.max_retries + 1):
        user = base_user if attempt == 0 else base_user + _CORRECTIVE
        try:
            return parse_verdict(client.judge(system, user, cfg))
        except (ValueError, JudgeError) as e:  # bad JSON / missing keys / transport
            last = str(e)
    return _judge_error(last or "unparseable verdict after retry")


class HttpJudgeClient:  # pragma: no cover - exercised only with real keys
    """Minimal keyed provider client (urllib, no extra deps). Nightly/release only."""

    def judge(self, system: str, user: str, cfg: JudgeConfig) -> dict:
        if cfg.provider == "anthropic":
            return self._anthropic(system, user, cfg)
        return self._openai(system, user, cfg)

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001 - normalize all transport faults
            raise JudgeError(f"provider transport: {e}") from e

    def _openai(self, system: str, user: str, cfg: JudgeConfig) -> dict:
        key = os.environ[PROVIDER_KEYS["openai"]]
        body = self._post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            {
                "model": cfg.model,
                "temperature": cfg.temperature,
                "max_tokens": cfg.max_tokens,
                "seed": cfg.seed,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        return json.loads(body["choices"][0]["message"]["content"])

    def _anthropic(self, system: str, user: str, cfg: JudgeConfig) -> dict:
        key = os.environ[PROVIDER_KEYS["anthropic"]]
        body = self._post(
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            {
                "model": cfg.model,
                "system": system,
                "max_tokens": cfg.max_tokens,
                "temperature": cfg.temperature,
                "messages": [{"role": "user", "content": user}],
            },
        )
        return json.loads(body["content"][0]["text"])
