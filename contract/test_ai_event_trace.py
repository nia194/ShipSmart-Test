"""Contract: ShipSmart-API ``AIEvent`` <-> evals ``EvalTrace`` correlation keys.

The guardrails doc's production ``AIEvent`` (§5.8/Appendix) and the evals doc's
``EvalTrace`` (§3.4) must share the correlation payload so the Layer-6 online loop
can sample a production event and replay it as an eval run. Some keys are renamed
across the two docs (``sources``/``source_ids``, ``tokens``/``token_count``,
``cost_usd``/``cost_estimate_usd``) — this pins that mapping so a rename on either
side fails CI. (This is cross-doc reconciliation #4.)
"""

from __future__ import annotations

from dataclasses import fields

from evals.trace import EvalTrace
from sibling import API, py_model_fields, read

# EvalTrace field name -> AIEvent field name (the same correlation key, per doc).
CORRELATION = {
    "decisions": "decisions",
    "tool_calls": "tool_calls",
    "provider": "provider",
    "model": "model",
    "prompt_version": "prompt_version",
    "latency_ms": "latency_ms",
    "sources": "source_ids",
    "tokens": "token_count",
    "cost_usd": "cost_estimate_usd",
}


def test_ai_event_and_eval_trace_share_correlation_keys():
    eval_fields = {f.name for f in fields(EvalTrace)}
    ai_fields = py_model_fields(read(API / "app" / "schemas" / "ai_event.py"), "AIEvent")

    missing_eval = sorted(e for e in CORRELATION if e not in eval_fields)
    missing_ai = sorted(a for a in CORRELATION.values() if a not in ai_fields)

    assert not missing_eval, f"EvalTrace missing correlation fields: {missing_eval}"
    assert not missing_ai, (
        f"AIEvent missing correlation fields (online sampling -> eval replay breaks): {missing_ai}"
    )
