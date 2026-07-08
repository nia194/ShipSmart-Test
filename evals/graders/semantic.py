"""Semantic RAG metrics (evals guide §5.2).

Context recall and context precision are LABEL-based, so they are deterministic
and keyless (computable from ``relevant_doc_ids`` + the retrieved set) — this is
the v2 addition that keeps two of the four Ragas-style metrics judge-free.
Answer-relevance (embedding similarity) needs a real embedding provider and only
runs in the nightly/release lanes; it is a guarded stub here.
"""

from __future__ import annotations

from ..case_model import Case
from ..protocol import Response
from . import Verdict


def context_recall(relevant: list[str], retrieved: list[str]) -> float:
    if not relevant:
        return 1.0
    hit = len(set(relevant) & set(retrieved))
    return hit / len(set(relevant))


def context_precision(relevant: list[str], retrieved: list[str]) -> float:
    """Rank-weighted precision: relevant chunks ranked above irrelevant ones."""
    if not retrieved:
        return 0.0
    rel = set(relevant)
    hits = 0
    weighted = 0.0
    for i, doc in enumerate(retrieved, 1):
        if doc in rel:
            hits += 1
            weighted += hits / i
    return weighted / min(len(rel), len(retrieved)) if rel else 0.0


def grade(case: Case, resp: Response, *, min_recall: float = 0.90) -> Verdict:
    """Deterministic label-based grade (recall gate). Keyless."""
    rel = case.expected.relevant_doc_ids
    recall = context_recall(rel, resp.retrieved_doc_ids)
    precision = context_precision(rel, resp.retrieved_doc_ids)
    passed = recall >= min_recall
    return Verdict(
        passed=passed,
        grader="semantic",
        reason=f"recall={recall:.2f} precision={precision:.2f} (min_recall={min_recall})",
        score=recall,
    )


def answer_relevance(resp: Response, query: str) -> float:  # pragma: no cover - needs keys
    """Embedding similarity of answer to question — nightly/release only."""
    raise NotImplementedError(
        "answer_relevance needs a real embedding provider; runs in nightly/release, not CI"
    )
