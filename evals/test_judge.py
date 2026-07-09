"""LLM-judge + calibration tests (evals §10, §12).

Everything here is keyless: the judge's prompt/parse/retry logic is exercised with
a fake client, and the calibration math is pure. Covers the invariants that make
the judge safe to gate on — never grades Layer-4 safety, never silently passes on
a bad verdict, stays keyless in CI, and its rubric templates stay version-pinned.
"""

from __future__ import annotations

import pytest

from evals import calibration
from evals.case_model import Case, Expected
from evals.graders import llm_judge
from evals.graders.llm_judge import JudgeError
from evals.manifest import load_manifest
from evals.protocol import Response


def _case(*, layer=5, rubric="Explanation cites the real factors and makes no guarantee."):
    return Case(
        id="j-1",
        layer=layer,
        suite="product/journeys",
        dataset_version="v1.0",
        split="dev",
        provenance="authored",
        added_in="v1.0",
        flaky=False,
        runs=1,
        input={"query": "why this carrier?"},
        expected=Expected(behavior="grounded_answer", judge_rubric=rubric),
        severity="minor",
        tags=[],
    )


class _Fake:
    """Returns/raises the scripted items in order; repeats the last one."""

    def __init__(self, *scripted):
        self.scripted = list(scripted)
        self.calls = 0

    def judge(self, system, user, cfg):
        item = self.scripted[min(self.calls, len(self.scripted) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


_GOOD = {"score": 0.9, "verdict": "pass", "reasoning": "grounded", "violations": []}
_BAD = {"score": 0.2, "verdict": "fail", "reasoning": "overclaims", "violations": ["guarantee"]}


# ── prompt + verdict parsing ──────────────────────────────────────────────────
def test_build_user_prompt_carries_rubric_and_response():
    p = llm_judge.build_user_prompt("MY RUBRIC", "the answer text")
    assert "MY RUBRIC" in p and "the answer text" in p and "JSON" in p


def test_parse_verdict_maps_pass_and_fail():
    assert llm_judge.parse_verdict(_GOOD).passed is True
    assert llm_judge.parse_verdict(_BAD).passed is False


@pytest.mark.parametrize(
    "obj",
    [
        {"score": 1.0, "verdict": "pass"},  # missing keys
        {"score": 2.0, "verdict": "pass", "reasoning": "", "violations": []},  # out of range
        {"score": 1.0, "verdict": "maybe", "reasoning": "", "violations": []},  # bad verdict
    ],
)
def test_parse_verdict_rejects_malformed(obj):
    with pytest.raises(ValueError):
        llm_judge.parse_verdict(obj)


# ── grade() behavior ──────────────────────────────────────────────────────────
def test_grade_passes_with_a_valid_verdict():
    resp = Response(text="because price + transit")
    v = llm_judge.grade(_case(), resp, judge_client=_Fake(_GOOD))
    assert v.passed and v.grader == "llm_judge" and v.score == 0.9


def test_grade_retries_once_then_succeeds():
    fake = _Fake({"score": 1.0}, _GOOD)  # first malformed, second valid
    v = llm_judge.grade(_case(), Response(text="x"), judge_client=fake)
    assert v.passed and fake.calls == 2


def test_grade_two_bad_verdicts_becomes_judge_error_not_a_pass():
    fake = _Fake({"score": 1.0}, {"nope": 1})  # both malformed
    v = llm_judge.grade(_case(), Response(text="x"), judge_client=fake)
    assert not v.passed and v.reason.startswith("judge_error:")


def test_grade_transport_failure_becomes_judge_error():
    fake = _Fake(JudgeError("500"), JudgeError("500"))
    v = llm_judge.grade(_case(), Response(text="x"), judge_client=fake)
    assert not v.passed and "judge_error" in v.reason


def test_judge_never_decides_layer4_safety():
    v = llm_judge.grade(_case(layer=4), Response(text="x"), judge_client=_Fake(_GOOD))
    assert not v.passed and "safety" in v.reason


def test_grade_without_a_client_is_judge_error_not_a_pass():
    # No client passed and no key in the env (hermetic fixture) -> judge_error.
    v = llm_judge.grade(_case(), Response(text="x"))
    assert not v.passed and "no judge client" in v.reason


# ── keyless / availability ────────────────────────────────────────────────────
def test_unavailable_without_keys():
    assert llm_judge.available() is False
    assert llm_judge.get_judge_client() is None


def test_available_when_a_provider_key_is_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert llm_judge.available() is True


# ── rubric templates + safety-dataset invariant ───────────────────────────────
def test_rubric_templates_exist_for_every_pinned_version():
    cfg = llm_judge.load_judge_config()
    assert cfg.rubric_versions, "no rubric versions pinned"
    for name in cfg.rubric_versions:
        assert llm_judge.load_rubric(name).strip(), f"rubric template {name}.md missing/empty"


def test_no_safety_case_carries_a_judge_rubric():
    # Structural enforcement of "judge never decides safety": Layer-4 datasets must
    # not declare a judge_rubric, so the judge is never even invoked on them.
    from evals.case_model import load_jsonl

    offenders = []
    for entry in load_manifest():
        if entry.layer == 4:
            offenders += [c.id for c in load_jsonl(entry.path) if c.expected.judge_rubric]
    assert not offenders, f"Layer-4 safety cases must not carry a judge_rubric: {offenders}"


def test_judge_version_is_stamped_and_stable():
    cfg = llm_judge.load_judge_config()
    assert cfg.judge_version.startswith(f"{cfg.provider}/{cfg.model}@[")


# ── calibration math (IRR) ────────────────────────────────────────────────────
def test_raw_agreement_and_kappa_on_perfect_agreement():
    a = ["pass", "fail", "pass", "fail"]
    assert calibration.raw_agreement(a, a) == 1.0
    assert calibration.cohens_kappa(a, a) == 1.0


def test_kappa_is_zero_at_chance():
    # Raters independent with the same 50/50 marginal -> kappa ~ 0.
    a = ["pass", "pass", "fail", "fail"]
    b = ["pass", "fail", "pass", "fail"]
    assert calibration.raw_agreement(a, b) == 0.5
    assert abs(calibration.cohens_kappa(a, b)) < 1e-9


def test_calibrate_freezes_below_threshold():
    a = ["pass"] * 8 + ["fail", "fail"]
    b = ["pass"] * 6 + ["fail"] * 4  # 8/10 agree
    ok = calibration.calibrate("explanation_quality", a, b, min_agreement=0.80)
    assert ok.passed and ok.verdict == "ok" and ok.raw_agreement == 0.8
    strict = calibration.calibrate("explanation_quality", a, b, min_agreement=0.90)
    assert not strict.passed and strict.verdict == "FREEZE_RUBRIC"


def test_calibrate_rejects_mismatched_rater_lengths():
    with pytest.raises(ValueError):
        calibration.raw_agreement(["pass"], ["pass", "fail"])
