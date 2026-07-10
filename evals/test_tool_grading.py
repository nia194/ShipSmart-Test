"""Layer-3 tool-selection grading (evals §6.1 — the forbidden-tool loud failure)."""

from __future__ import annotations

from evals.case_model import Case, Expected
from evals.graders import rule_based
from evals.protocol import EchoSUT, Response


def _case(**exp) -> Case:
    return Case(
        id="a-1", layer=3, suite="agent/tool_use", dataset_version="v1.0", split="dev",
        provenance="authored", added_in="v1.0", flaky=False, runs=1,
        input={"query": "q"}, expected=Expected(behavior=exp.pop("behavior", "tool_call"), **exp),
        severity="major", tags=["agent:plan"],
    )


def _resp(**kw) -> Response:
    return Response(text="echo", **kw)


def test_required_tool_missing_fails():
    v = rule_based.grade(_case(required_tools=["get_quote_preview"]), _resp(tool_calls=[]))
    assert not v.passed and "required tools not called" in v.reason


def test_required_tool_present_passes():
    c = _case(required_tools=["get_quote_preview"])
    v = rule_based.grade(c, _resp(tool_calls=["get_quote_preview"]))
    assert v.passed


def test_forbidden_tool_executing_fails_loudly():
    c = _case(behavior="clarify", forbidden_tools=["get_quote_preview"])
    v = rule_based.grade(c, _resp(tool_calls=["get_quote_preview"]))
    assert not v.passed and "forbidden tool executed" in v.reason


def test_max_steps_exceeded_fails():
    v = rule_based.grade(_case(max_steps=2), _resp(tool_calls=["a", "b", "c"], steps=3))
    assert not v.passed and "exceeds max_steps" in v.reason


def test_required_and_forbidden_tags():
    ok = rule_based.grade(
        _case(required_tags=["agent:tool"]), _resp(decisions=["agent:tool"])
    )
    assert ok.passed
    bad = rule_based.grade(
        _case(forbidden_tags=["agent:fallback"]), _resp(decisions=["agent:fallback"])
    )
    assert not bad.passed and "forbidden tags emitted" in bad.reason


def test_echo_sut_satisfies_its_own_tool_assertions():
    # The stub SUT must keep the CI lane green under the new assertions.
    c = _case(required_tools=["get_quote_preview"], required_tags=["agent:tool"], max_steps=3)
    v = rule_based.grade(c, EchoSUT()(c))
    assert v.passed


def test_echo_sut_refusal_calls_no_tools():
    c = _case(behavior="refusal", forbidden_tools=["get_quote_preview"])
    resp = EchoSUT()(c)
    assert resp.tool_calls == [] and rule_based.grade(c, resp).passed
