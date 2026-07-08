"""Contract: every decision tag ShipSmart-API emits is registered in the vocabulary.

The ``guardrail:* / agent:* / …`` tags are the audit language AND the §13 coverage
join key — a tag emitted in code that ``evals/tag_vocabulary.yml`` doesn't list is
silent drift that breaks Layer-3/4 grading and coverage. This is evals §4.2.
"""

from __future__ import annotations

from evals import tags as vocab
from sibling import api_decision_tags


def test_emitted_decision_tags_are_registered():
    known = vocab.known_tags()
    namespaces = vocab.namespaces()
    unknown_namespace: set[str] = set()
    unregistered: set[str] = set()

    for tag in api_decision_tags():
        ns, base = tag.split(":", 1)
        if ns not in namespaces:
            unknown_namespace.add(tag)
        elif base != "*" and tag not in known:
            unregistered.add(tag)

    assert not unknown_namespace, (
        f"tags emitted in an unregistered namespace (add it to tag_vocabulary.yml + "
        f"sibling._TAG_NAMESPACES): {sorted(unknown_namespace)}"
    )
    assert not unregistered, (
        f"tags emitted by ShipSmart-API but missing from evals/tag_vocabulary.yml: "
        f"{sorted(unregistered)}"
    )


def test_coverage_control_tags_are_registered():
    """Every guardrail tag coverage.yml joins on must exist in the vocabulary."""
    import yaml

    from evals.manifest import DATASETS_DIR

    cov = yaml.safe_load((DATASETS_DIR.parent / "coverage.yml").read_text(encoding="utf-8"))
    known = vocab.known_tags()
    referenced = {
        c["tag"]
        for group in ("controls", "conditional")
        for c in (cov.get(group) or {}).values()
        if c.get("tag")
    }
    missing = referenced - known
    assert not missing, f"coverage.yml references tags not in tag_vocabulary.yml: {sorted(missing)}"
