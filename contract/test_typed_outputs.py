"""Contract: ShipSmart-API typed-output schemas <-> ShipSmart-Web TS interfaces.

The AI boundary returns typed data (guardrails §5.3); a field rename on either
side would silently break the product's ability to render/reject model output.
Parsed from source as text — no services, no imports across repos.
"""

from __future__ import annotations

import pytest

from sibling import API, WEB, py_model_fields, read, ts_interface_fields

MODELS = [
    "AssistantResponse",
    "FieldPatch",
    "FormPatchProposal",
    "ToolCallPolicy",
    "SourceCitation",
    "Action",
    # Product Roadmap §6 typed result union + transparency (additive contract).
    "NextQuestion",
    "ShippingOptionResult",
    "ComparisonResult",
    "MissingInfoResult",
    "PolicyAnswerResult",
    "ToolCallTrace",
    "AssistantAudit",
    # Grid action bus (§6/§12).
    "GridFilter",
    "SortGridAction",
    "FilterGridAction",
    "SuggestAction",
]


@pytest.fixture(scope="module")
def api_src() -> str:
    return read(API / "app" / "schemas" / "typed_outputs.py")


@pytest.fixture(scope="module")
def web_src() -> str:
    return read(WEB / "src" / "lib" / "typed-outputs.ts")


@pytest.mark.parametrize("model", MODELS)
def test_typed_output_fields_match(model: str, api_src: str, web_src: str):
    py = py_model_fields(api_src, model)
    ts = ts_interface_fields(web_src, model)
    assert py == ts, f"{model}: API {sorted(py)} != Web {sorted(ts)}"
