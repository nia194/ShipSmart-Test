"""
Cross-repo CONTRACT tests (no services running).

Parse the sibling repos' source files and assert the wire shapes line up, so a
field rename in one repo can't silently break a consumer in another.
"""

from __future__ import annotations

import re

from sibling import (
    API,
    INFRA,
    JAVA,
    MCP,
    WEB,
    java_record_components,
    json_schema_required,
    py_model_fields,
    read,
    ts_interface_fields,
)

WEB_ADVISOR = read(WEB / "src/lib/advisor-api.ts")
API_SCHEMAS = read(API / "app/schemas/advisor.py")
WEB_COMPARE = read(WEB / "src/components/shipping/compare.types.ts")
API_COMPARE = read(API / "app/schemas/compare.py")

QUOTE_REQ = {"origin_zip", "destination_zip", "weight_lbs", "length_in", "width_in", "height_in"}
ADDR_REQ = {"street", "city", "state", "zip_code"}
SHIPMENT_FIELDS = {
    "id", "origin", "destination", "dropOffDate", "expectedDeliveryDate",
    "totalWeight", "totalItems", "status", "version", "createdAt", "updatedAt",
}


# ── Advisor response shapes: ShipSmart-API ↔ ShipSmart-Web (E tags included) ──


def test_decision_path_shape_matches_api_and_web():
    api = py_model_fields(API_SCHEMAS, "DecisionPath")
    web = ts_interface_fields(WEB_ADVISOR, "DecisionPath")
    assert api == web == {"mode", "retrieval", "answer", "provider", "tags"}


def test_shipping_advisor_response_matches():
    api = py_model_fields(API_SCHEMAS, "ShippingAdvisorResponse")
    web = ts_interface_fields(WEB_ADVISOR, "ShippingAdvisorResponse")
    assert api == web
    assert {"answer", "reasoning_summary", "tools_used", "sources",
            "context_used", "decision_path"} <= api


def test_tracking_advisor_response_matches():
    api = py_model_fields(API_SCHEMAS, "TrackingAdvisorResponse")
    web = ts_interface_fields(WEB_ADVISOR, "TrackingAdvisorResponse")
    assert api == web
    assert {"guidance", "issue_summary", "tools_used", "sources",
            "next_steps", "decision_path"} <= api


def test_advisor_source_shape_matches():
    web = ts_interface_fields(WEB_ADVISOR, "AdvisorSource")
    assert web == {"source", "chunk_index", "score"}
    rag = read(API / "app/services/rag_service.py")
    assert '"source": r.source' in rag
    assert '"chunk_index": r.chunk_index' in rag
    assert '"score":' in rag


# ── Shipment DTO: ShipSmart-Orchestrator ↔ ShipSmart-Web ─────────────────────


def test_shipment_dto_matches_java_and_web():
    java = java_record_components(
        read(JAVA / "src/main/java/com/shipsmart/api/dto/ShipmentSummaryDto.java"),
        "ShipmentSummaryDto",
    )
    web = ts_interface_fields(WEB_ADVISOR, "ShipmentSummary")
    assert java == SHIPMENT_FIELDS
    assert web == SHIPMENT_FIELDS


# ── Compare cockpit: ShipSmart-Web compare.types.ts ↔ ShipSmart-API compare.py ─

COMPARE_OPTION_FIELDS = {
    "id", "carrier", "service_name", "carrier_type", "price_usd",
    "arrival_date", "arrival_label", "transit_days", "guaranteed",
}
COMPARE_SHIPMENT_FIELDS = {
    "item_description", "origin_zip", "destination_zip", "deadline_date", "weight_lb",
}


def test_compare_option_shape_matches_api_and_web():
    web = ts_interface_fields(WEB_COMPARE, "CompareOption")
    api = py_model_fields(API_COMPARE, "CompareOption")
    assert web == api == COMPARE_OPTION_FIELDS


def test_compare_shipment_web_fields_are_accepted_by_api():
    # The frontend posts these shipment fields; ShipSmart-API's ShipmentContext
    # must accept every one (it may carry additional optional fields, e.g.
    # declared_value_usd, which the web client simply omits).
    web = ts_interface_fields(WEB_COMPARE, "Shipment")
    api = py_model_fields(API_COMPARE, "ShipmentContext")
    assert web == COMPARE_SHIPMENT_FIELDS
    assert web <= api


# ── MCP tool schemas: MCP ↔ API test double ↔ Web context ────────────────────


def test_mcp_tool_schemas_are_canonical():
    qreq, qprops = json_schema_required(read(MCP / "app/tools/quote_tools.py"), "GetQuotePreviewTool")
    areq, aprops = json_schema_required(read(MCP / "app/tools/address_tools.py"), "ValidateAddressTool")
    assert qreq == QUOTE_REQ and qprops == QUOTE_REQ
    assert areq == ADDR_REQ and aprops == (ADDR_REQ | {"country"})


def _conftest_required(src: str, tool: str) -> set[str]:
    m = re.search(rf'"name":\s*"{tool}".*?"required":\s*\[(.*?)\]', src, re.S)
    assert m, f"{tool} not found in API conftest mock"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def test_api_test_double_matches_mcp():
    conf = read(API / "tests/conftest.py")
    assert _conftest_required(conf, "get_quote_preview") == QUOTE_REQ
    assert _conftest_required(conf, "validate_address") == ADDR_REQ


def test_web_advisor_context_keys_are_accepted_by_quote_tool():
    ctx = ts_interface_fields(WEB_ADVISOR, "AdvisorContext")
    _, qprops = json_schema_required(read(MCP / "app/tools/quote_tools.py"), "GetQuotePreviewTool")
    forwarded = {k for k in ctx if k in qprops}
    assert {"origin_zip", "destination_zip", "weight_lbs"} <= forwarded


# ── Infra lexical function ↔ API SQL ─────────────────────────────────────────


def test_infra_lexical_fn_matches_api_sql():
    mig = read(INFRA / "supabase/migrations/20260529120000_rag_chunks_hybrid_lexical.sql")
    pg = read(API / "app/rag/pgvector_store.py")
    assert "match_rag_chunks_lexical(" in mig
    assert re.search(
        r"RETURNS TABLE\s*\(\s*id\b.*source\b.*chunk_index\b.*text\b.*score\b", mig, re.S,
    ), "lexical fn must return (id, source, chunk_index, text, score)"
    assert "match_rag_chunks_lexical($1, $2)" in pg
    assert "source, chunk_index, text, score" in pg
