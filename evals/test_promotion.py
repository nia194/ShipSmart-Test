"""Online-loop promotion pipeline tests (evals §14 — F10). Keyless."""

from __future__ import annotations

import json

import pytest

from evals import promotion
from evals.case_model import Case, Expected


def _event(intent: str, request_id: str = "r1", comment: str = "") -> dict:
    return {
        "request_id": request_id,
        "session_id_hash": "hash-abc",
        "route": "/api/v1/feedback" if intent.startswith("feedback") else "/api/v1/agent/run",
        "intent": intent,
        "decisions": ["agent:plan"],
        "feedback_comment": comment,
    }


# ── deterministic shadow sampling ─────────────────────────────────────────────
def test_negative_feedback_is_always_sampled():
    assert promotion.should_sample(_event("feedback:down:wrong_answer"), rate=0.0)


def test_sampling_is_deterministic_and_rate_bounded():
    events = [_event("agent:query", request_id=f"r{i}") for i in range(400)]
    picked_a = [e["request_id"] for e in events if promotion.should_sample(e, rate=0.05)]
    picked_b = [e["request_id"] for e in events if promotion.should_sample(e, rate=0.05)]
    assert picked_a == picked_b, "hash-based sampling must be reproducible"
    assert 0 < len(picked_a) < 60, f"5% of 400 should land near 20, got {len(picked_a)}"
    # rate=1 -> everything; rate=0 -> nothing (for non-feedback events)
    assert all(promotion.should_sample(e, rate=1.0) for e in events)
    assert not any(promotion.should_sample(e, rate=0.0) for e in events)


def test_build_review_queue_carries_the_redacted_comment():
    events = [
        _event("feedback:down:wrong_answer", comment="price was wrong for [EMAIL]"),
        _event("agent:query", request_id="never-sampled"),
    ]
    items = promotion.build_review_queue(events, rate=0.0)
    assert len(items) == 1
    item = items[0]
    assert item.intent == "feedback:down:wrong_answer"
    assert item.feedback_comment == "price was wrong for [EMAIL]"
    assert item.status == "pending" and len(item.key) == 16


def test_write_review_queue_appends_jsonl(tmp_path):
    items = promotion.build_review_queue([_event("feedback:down")], rate=0.0)
    path = tmp_path / "queue.jsonl"
    promotion.write_review_queue(items, path)
    promotion.write_review_queue(items, path)  # append, not overwrite
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["status"] == "pending"


# ── promotion produces valid, provenance-tagged cases ─────────────────────────
def test_to_candidate_case_is_a_valid_online_promoted_case():
    item = promotion.build_review_queue([_event("feedback:down:wrong_answer")], rate=0.0)[0]
    obj = promotion.to_candidate_case(
        item,
        case_id="rag-policy-0006",
        suite="rag/policy",
        layer=2,
        behavior="grounded_answer",
        query="what did the user actually ask",
        added_in="v1.1",
    )
    assert obj["provenance"] == "online_promoted" and obj["split"] == "dev"
    assert obj["input"]["review_key"] == item.key
    # round-trips through the real case model (what load_jsonl would do)
    case = Case(
        id=obj["id"], layer=obj["layer"], suite=obj["suite"],
        dataset_version=obj["dataset_version"], split=obj["split"],
        provenance=obj["provenance"], added_in=obj["added_in"], flaky=obj["flaky"],
        runs=obj["runs"], input=obj["input"],
        expected=Expected(behavior=obj["expected"]["behavior"]), severity=obj["severity"],
        tags=obj["tags"],
    )
    assert case.provenance == "online_promoted"


def test_malformed_promotion_fails_at_build_time():
    item = promotion.build_review_queue([_event("feedback:down")], rate=0.0)[0]
    with pytest.raises(ValueError):
        promotion.to_candidate_case(
            item,
            case_id="x-1",
            suite="rag/policy",
            layer=9,  # invalid layer -> Case.__post_init__ raises
            behavior="grounded_answer",
            query="q",
            added_in="v1.1",
        )
