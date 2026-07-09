"""The §13 completeness gate — coverage.yml is continuously enforced, not decorative.

Reading the two governance PDFs together, this is the join that makes them one
system: every release-gated guardrail CONTROL must be backed by either enough
adversarial eval cases (behavioral) or a live code test (structural). This fails
the build when a control drops below min_cases, points at a retired case, carries
a tag the vocabulary doesn't know, or (structural) loses the test/emit-site that
proves it. Keyless: parses datasets + API source as text.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml

from evals import tags as vocab
from evals.case_model import load_jsonl
from evals.manifest import load_manifest, verify
from sibling import API

COVERAGE = Path(__file__).resolve().parents[1] / "evals" / "coverage.yml"


def _coverage() -> dict:
    return yaml.safe_load(COVERAGE.read_text(encoding="utf-8"))


def _all_cases() -> list:
    cases: list = []
    for entry in load_manifest():
        verify(entry)  # sha256 must match before we trust the contents
        cases.extend(load_jsonl(entry.path))
    return cases


def _every_control() -> dict:
    cov = _coverage()
    return {**(cov.get("controls") or {}), **(cov.get("conditional") or {})}


def test_coverage_tags_are_registered():
    known = vocab.known_tags()
    bad = [
        f"{name} -> {c['tag']}" for name, c in _every_control().items() if c["tag"] not in known
    ]
    assert not bad, "coverage.yml tags absent from tag_vocabulary.yml:\n" + "\n".join(bad)


def test_case_guardrail_tags_are_registered():
    # Any guardrail:* tag a dataset case carries must be a known tag — catch typos
    # that would otherwise make a case silently uncounted by a control.
    known = vocab.known_tags()
    bad = {
        f"{c.id}: {t}"
        for c in _all_cases()
        for t in c.tags
        if t.startswith("guardrail:") and t not in known
    }
    assert not bad, "cases carry unregistered guardrail tags:\n" + "\n".join(sorted(bad))


def test_behavioral_controls_meet_min_cases():
    cases = _all_cases()
    by_id = {c.id: c for c in cases}
    by_tag: dict[str, list[str]] = defaultdict(list)
    for c in cases:
        if c.flaky:  # flaky cases are quarantined from the coverage gate
            continue
        for t in c.tags:
            by_tag[t].append(c.id)

    problems: list[str] = []
    for name, control in _coverage()["controls"].items():
        if control.get("kind") != "behavioral":
            continue
        found = by_tag.get(control["tag"], [])
        if len(found) < control["min_cases"]:
            problems.append(
                f"{name}: only {len(found)} case(s) carry {control['tag']}, "
                f"min_cases={control['min_cases']}"
            )
        for cid in control.get("case_ids", []):
            if cid not in by_id:
                problems.append(f"{name}: retired/unknown case_id {cid!r}")
            elif control["tag"] not in by_id[cid].tags:
                problems.append(f"{name}: {cid} does not carry {control['tag']}")

    assert not problems, "§13 coverage gaps:\n" + "\n".join(problems)


def test_structural_controls_stay_wired_and_tested():
    app_src = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore") for p in sorted((API / "app").rglob("*.py"))
    )
    problems: list[str] = []
    for name, control in _coverage()["controls"].items():
        if control.get("kind") != "structural":
            continue
        verified_by = control.get("verified_by", "")
        if not verified_by or not (API / verified_by).exists():
            problems.append(f"{name}: verified_by test {verified_by!r} is missing")
        if control["tag"] not in app_src:
            problems.append(f"{name}: tag {control['tag']} is no longer emitted in API app source")

    assert not problems, "structural control gaps:\n" + "\n".join(problems)
