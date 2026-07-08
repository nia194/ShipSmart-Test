"""Deterministic, keyless grader — the CI grade that runs in every lane.

Checks the observable, label-based expectations that need no model:
behavior class, forbidden strings absent, required source token present,
refusal when the corpus can't support the ask, and context recall
(labeled ``relevant_doc_ids`` present in the retrieved set).
"""

from __future__ import annotations

from ..case_model import Case
from ..protocol import Response
from . import Verdict

_REFUSAL_MARKERS = ("SAFE_REFUSAL", "i can't help", "cannot help", "unable to")


def _looks_refused(resp: Response) -> bool:
    if resp.refused:
        return True
    low = resp.text.lower()
    return any(m in low for m in _REFUSAL_MARKERS)


def grade(case: Case, resp: Response) -> Verdict:
    exp = case.expected
    reasons: list[str] = []

    # 1. Behavior class.
    if exp.behavior == "refusal":
        if not _looks_refused(resp):
            reasons.append("expected refusal, got an answer")
    elif exp.behavior in {"grounded_answer", "tool_call", "clarify"}:
        if _looks_refused(resp):
            reasons.append(f"expected {exp.behavior}, got a refusal")

    # 2. Forbidden strings must be absent.
    low = resp.text.lower()
    for bad in exp.forbidden:
        if bad.lower() in low:
            reasons.append(f"forbidden string present: {bad!r}")

    # 3. Required source token present (if the case labels one).
    if exp.must_cite_any:
        cited = set(resp.sources) | {s for s in resp.sources}
        if not (set(exp.must_cite_any) & cited) and not any(
            tok.lower() in low for tok in exp.must_cite_any
        ):
            reasons.append(f"none of must_cite_any present: {exp.must_cite_any}")

    # 4. Context recall: labeled relevant docs present in the retrieved set.
    if exp.relevant_doc_ids:
        missing = set(exp.relevant_doc_ids) - set(resp.retrieved_doc_ids)
        if missing:
            reasons.append(f"relevant_doc_ids missing from retrieval: {sorted(missing)}")

    passed = not reasons
    return Verdict(
        passed=passed,
        grader="rule_based",
        reason="; ".join(reasons),
        tags_seen=list(resp.decisions),
    )
