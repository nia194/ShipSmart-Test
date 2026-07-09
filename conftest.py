"""Test-suite guardrail: no test may reach a live LLM-judge provider.

The nightly/release lane runs (and the grader tests) must stay deterministic and
free regardless of whatever keys happen to be in the developer's environment. This
autouse fixture strips the provider keys for every test, so ``llm_judge.available()``
is False by default; tests that specifically exercise availability opt a key back
in with their own ``monkeypatch.setenv``.
"""

from __future__ import annotations

import pytest

from evals.graders import llm_judge


@pytest.fixture(autouse=True)
def _hermetic_judge(monkeypatch):
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    llm_judge.get_judge_client.cache_clear()
    yield
    llm_judge.get_judge_client.cache_clear()
