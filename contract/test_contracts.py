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
    py_class_fields,
    py_model_fields,
    read,
    ts_interface_fields,
)

WEB_ADVISOR = read(WEB / "src/lib/advisor-api.ts")
API_SCHEMAS = read(API / "app/schemas/advisor.py")
WEB_COMPARE = read(WEB / "src/components/shipping/compare.types.ts")
API_COMPARE = read(API / "app/schemas/compare.py")
API_INFO = read(API / "app/api/routes/info.py")
API_CONFIG = read(API / "app/core/config.py")
WEB_CONFIG = read(WEB / "src/config/api.ts")

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
    qreq, qprops = json_schema_required(
        read(MCP / "app/tools/quote_tools.py"), "GetQuotePreviewTool"
    )
    areq, aprops = json_schema_required(
        read(MCP / "app/tools/address_tools.py"), "ValidateAddressTool"
    )
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


# ── Workflow + compliance: ShipSmart-API ↔ ShipSmart-Web (UC2/UC3/UC4) ───────

WEB_WORKFLOW = read(WEB / "src/lib/workflow-api.ts")
API_WORKFLOW_SCHEMAS = read(API / "app/schemas/workflow.py")
API_WORKFLOW_STATE = read(API / "app/workflow/state.py")
API_DOMAIN_MODELS = read(API / "app/domain/models.py")

WORKFLOW_RESPONSE_FIELDS = {
    "workflow_id", "status", "hs_code", "hs_title", "hs_candidates", "landed_cost",
    "carrier_quotes", "recommended_carrier", "compliance", "documents",
    "pending_review_areas", "officer_determination", "officer_note", "decisions",
}


def test_workflow_response_matches_api_and_web():
    api = py_model_fields(API_WORKFLOW_SCHEMAS, "WorkflowResponse")
    web = ts_interface_fields(WEB_WORKFLOW, "WorkflowResponse")
    assert api == web == WORKFLOW_RESPONSE_FIELDS


def test_workflow_process_request_matches():
    api = py_model_fields(API_WORKFLOW_SCHEMAS, "WorkflowProcessRequest")
    web = ts_interface_fields(WEB_WORKFLOW, "WorkflowProcessRequest")
    assert api == web == {
        "origin_country", "destination_country", "declared_value_usd",
        "weight_lbs", "description", "category",
    }


def test_workflow_review_request_matches():
    api = py_model_fields(API_WORKFLOW_SCHEMAS, "WorkflowReviewRequest")
    web = ts_interface_fields(WEB_WORKFLOW, "WorkflowReviewRequest")
    assert api == web == {"determination", "note"}


def test_compliance_summary_matches_api_and_web():
    api = py_model_fields(API_WORKFLOW_STATE, "ComplianceSummary")
    web = ts_interface_fields(WEB_WORKFLOW, "ComplianceSummary")
    assert api == web == {
        "verdict", "summary", "flagged_areas", "unverified_areas",
        "critique_rounds", "provider",
    }


def test_workflow_domain_models_match_api_and_web():
    expected = {
        "HsCandidate": {"hs_code", "title", "confidence"},
        "DutyQuote": {
            "hs_code", "destination", "value_usd", "duty_pct", "duty_usd",
            "tax_label", "tax_pct", "tax_usd", "total_landed_usd", "trade_note",
        },
        "CarrierQuote": {"carrier", "service", "price_usd", "estimated_days"},
        "GeneratedDoc": {"doc_type", "title", "fields"},
    }
    for name, fields in expected.items():
        api = py_class_fields(API_DOMAIN_MODELS, name)  # domain models subclass _Frozen
        web = ts_interface_fields(WEB_WORKFLOW, name)
        assert api == web == fields, name


def test_workflow_review_determination_literal_matches():
    # The officer determination is exactly cleared|blocked on both sides.
    assert 'Literal["cleared", "blocked"]' in API_WORKFLOW_SCHEMAS
    assert '"cleared" | "blocked"' in WEB_WORKFLOW


# ── Conversational Concierge + hybrid sync: ShipSmart-API ↔ ShipSmart-Web ─────

API_CONCIERGE_SCHEMAS = read(API / "app/schemas/concierge.py")
API_CONCIERGE_MODELS = read(API / "app/agents/concierge/models.py")
WEB_CONCIERGE = read(WEB / "src/lib/concierge-api.ts")
WEB_DRAFT = read(WEB / "src/state/shipmentDraft.ts")


def _api_slot_keys() -> set[str]:
    m = re.search(r"SLOT_KEYS:[^=]*=\s*\((.*?)\)", API_CONCIERGE_MODELS, re.S)
    assert m, "SLOT_KEYS tuple not found in concierge models"
    return set(re.findall(r'"([a-z_]+)"', m.group(1)))


def _web_slot_keys() -> set[str]:
    m = re.search(r"SLOT_FIELD_MAP[^=]*=\s*\{(.*?)\n\}", WEB_DRAFT, re.S)
    assert m, "SLOT_FIELD_MAP not found in shipmentDraft.ts"
    return set(re.findall(r"^\s*([a-z_]+):", m.group(1), re.M))


def test_concierge_state_shape_matches_api_and_web():
    api = py_model_fields(API_CONCIERGE_SCHEMAS, "ConciergeState")
    web = ts_interface_fields(WEB_CONCIERGE, "ConciergeState")
    assert api == web == {"slots", "intent", "status", "pending_clarification", "turns"}


def test_concierge_response_shape_matches_api_and_web():
    api = py_model_fields(API_CONCIERGE_SCHEMAS, "ConciergeResponse")
    web = ts_interface_fields(WEB_CONCIERGE, "ConciergeResponse")
    assert api == web == {
        "reply", "state", "session_id", "clarification",
        "dispatched_to", "sources", "decisions", "provider", "assistant",
    }


def test_concierge_history_shape_matches_api_and_web():
    """The recall endpoint's payload (GET /concierge/{id}) agrees across API ↔ Web."""
    api = py_model_fields(API_CONCIERGE_SCHEMAS, "ConciergeHistoryResponse")
    web = ts_interface_fields(WEB_CONCIERGE, "ConciergeHistoryResponse")
    assert api == web == {"session_id", "state", "messages"}


# ── Reply-to-a-message: advisor + concierge speak the same reply context ──────

API_CHAT_SCHEMAS = read(API / "app/schemas/chat.py")


def test_reply_message_shape_matches_api_and_web():
    api = py_model_fields(API_CHAT_SCHEMAS, "ReplyMessage")
    web = ts_interface_fields(WEB_ADVISOR, "ReplyMessage")
    assert api == web == {"role", "text"}


def test_reply_context_request_fields_present_across_api_and_web():
    # API request schemas accept the reply context (advisor + concierge)...
    for src in (API_SCHEMAS, API_CONCIERGE_SCHEMAS):
        assert "reply_to" in src and "recent_history" in src, "API request missing reply fields"
    # ...and both Web chat clients send it.
    for src in (WEB_ADVISOR, WEB_CONCIERGE):
        assert "reply_to" in src and "recent_history" in src, "Web client missing reply fields"


def test_concierge_slot_superset_covers_web_draft_fields():
    api = _api_slot_keys()
    web = _web_slot_keys()
    # Every slot the Web ShipmentDraft maps to is a real server slot,
    assert web <= api, web - api
    # and the shared shipment-context core is present on both sides.
    assert {"origin", "destination", "weight_lbs", "priority",
            "description", "declared_value_usd"} <= web


# ── Shipping-scope policy: API publishes it; API + Web agree on the values ─────


def test_info_response_publishes_shipping_scope():
    """ShipSmart-API's /info contract exposes the mode for the frontend to read."""
    fields = py_model_fields(API_INFO, "InfoResponse")
    assert {"shipping_scope", "domestic_country"} <= fields, fields


def test_shipping_scope_literals_agree_across_api_and_web():
    """Both sides must speak the same two modes — guards against literal drift."""
    for src in (API_CONFIG, WEB_CONFIG):
        assert "worldwide" in src
        assert "domestic" in src
