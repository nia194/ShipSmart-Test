"""The Layer-6 online loop: shadow sampling → review queue → promotion (evals §14).

Production AIEvents (already pseudonymized + PII-redacted at write time) are
sampled into a human review queue; a reviewed item can be promoted into a real
dataset case with ``provenance: "online_promoted"``. Two rules make this safe:

* **Sampling is deterministic** — hash-based, not random — so re-running the
  sampler over the same event stream picks the same events (auditable, no
  seed-drift). Negative feedback (``feedback:down``) is ALWAYS sampled: a user
  complaint is a review candidate by definition.
* **Promotion is a reviewed diff, never an append.** This module only writes
  CANDIDATES (to the gitignored reports/ area). A human moves a candidate into
  a dataset file, bumps the dataset version, re-records the manifest sha256,
  and registers any guardrail tag in coverage.yml — the same ritual as any
  authored case. Nothing promotes itself.

This is cross-doc reconciliation #3: the evals promotion pipeline and the
guardrails feedback-triage queue are ONE path, fed by POST /api/v1/feedback
(ShipSmart-API) and the audit stream.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .case_model import Case, Expected

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
REVIEW_QUEUE = REPORTS_DIR / "review_queue.jsonl"

DEFAULT_SAMPLE_RATE = 0.05
_HASH_SPACE = float(1 << 32)


def _sample_key(event: dict) -> str:
    return "|".join(
        str(event.get(k, "")) for k in ("request_id", "session_id_hash", "route", "intent")
    )


def is_priority_signal(event: dict) -> bool:
    """The §9.2 always-sample signals: a user complaint or any guardrail firing.

    Covers user thumbs-down (``feedback:down``), any ``guardrail:*`` block/refusal
    tag in the decision path, and structured-output retries (also a ``guardrail:*``
    tag) — the events most likely to be a real, promotable failure.
    """
    if str(event.get("intent", "")).startswith("feedback:down"):
        return True
    tags = [*event.get("decisions", []), *event.get("guardrail_events", [])]
    return any(str(t).startswith("guardrail:") for t in tags)


def should_sample(event: dict, *, rate: float = DEFAULT_SAMPLE_RATE) -> bool:
    """Deterministic hash-based shadow sampling; priority signals are always in."""
    if is_priority_signal(event):
        return True
    digest = hashlib.sha256(_sample_key(event).encode()).hexdigest()
    return int(digest[:8], 16) / _HASH_SPACE < rate


@dataclass(frozen=True)
class ReviewItem:
    """One sampled event awaiting human review (already PII-safe upstream)."""

    key: str
    route: str
    intent: str
    decisions: list[str] = field(default_factory=list)
    feedback_comment: str = ""
    tags: list[str] = field(default_factory=list)  # feedback tags (§6.6 FeedbackEvent)
    # triage_status (§6.6): new -> reviewed -> promoted | rejected (set by the reviewer).
    status: str = "new"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def build_review_queue(
    events: list[dict], *, rate: float = DEFAULT_SAMPLE_RATE
) -> list[ReviewItem]:
    items = []
    for event in events:
        if should_sample(event, rate=rate):
            items.append(
                ReviewItem(
                    key=hashlib.sha256(_sample_key(event).encode()).hexdigest()[:16],
                    route=str(event.get("route", "")),
                    intent=str(event.get("intent", "")),
                    decisions=list(event.get("decisions", [])),
                    feedback_comment=str(event.get("feedback_comment", "")),
                    tags=list(event.get("feedback_tags", [])),
                )
            )
    return items


def write_review_queue(items: list[ReviewItem], path: str | Path = REVIEW_QUEUE) -> Path:
    """Append candidates to the (gitignored) review queue for the weekly session."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for item in items:
            fh.write(item.to_json_line() + "\n")
    return p


def to_candidate_case(
    item: ReviewItem,
    *,
    case_id: str,
    suite: str,
    layer: int,
    behavior: str,
    query: str,
    added_in: str,
    severity: str = "major",
    tags: list[str] | None = None,
) -> dict:
    """A reviewed item → a dataset-ready case dict (``provenance: online_promoted``).

    Validates through the real Case model so a malformed promotion fails HERE,
    not in the next lane run. The returned dict is what the reviewer pastes into
    the target ``*.vN.jsonl`` (then bumps version + manifest sha — reviewed diff).
    """
    case = Case(
        id=case_id,
        layer=layer,
        suite=suite,
        dataset_version=added_in,
        split="dev",  # promoted cases enter dev; holdout stays authored-only
        provenance="online_promoted",
        added_in=added_in,
        flaky=False,
        runs=1,
        input={"query": query, "review_key": item.key},
        expected=Expected(behavior=behavior),
        severity=severity,
        tags=list(tags or []),
    )
    return {
        "id": case.id,
        "layer": case.layer,
        "suite": case.suite,
        "dataset_version": case.dataset_version,
        "split": case.split,
        "provenance": case.provenance,
        "added_in": case.added_in,
        "flaky": case.flaky,
        "runs": case.runs,
        "input": case.input,
        "expected": {"behavior": behavior},
        "severity": case.severity,
        "tags": case.tags,
    }
