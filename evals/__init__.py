"""ShipSmart evaluation system — the cross-repo eval home.

Six layers (contract, rag, agent, safety, product, online) run in three lanes
(ci / nightly / release) over versioned JSONL datasets, graded by rule-based,
semantic, and LLM-judge graders, gated by the statistical rigor in ``rigor.py``,
and appended to ``reports/history.jsonl`` with a regenerated ``reports/trend.md``.

Foundation (F0) ships the mechanics; each later phase populates a layer's
datasets and graders. See ``evals/README.md``.
"""

__all__ = ["case_model", "trace", "tags", "rigor", "manifest"]
