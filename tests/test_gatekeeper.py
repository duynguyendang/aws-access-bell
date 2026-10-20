"""Gatekeeper tests: claim verification against resident-created context.

A stranger's words are never proof of identity. Only an expected window or a
calendar event the resident created can verify a claim; a previous label and an
unanalysed snapshot cannot.
"""

import json

from backend.llm.stub import StubLLM
from backend.triage import EnrichmentPipeline


def _event(raw, occurred_at="2026-09-15T10:00:00Z"):
    return dict(
        id=1,
        kind="ding",
        device_id="front_door",
        occurred_at=occurred_at,
        raw_json=json.dumps(raw),
        triage_json="{}",
    )


def _raw(hint=None, tags=None, statement=None):
    raw = {"meta": {}, "data": {"attributes": {}}}
    if hint:
        raw["data"]["attributes"]["label_hint"] = hint
    if tags:
        raw["meta"]["tags"] = tags
    if statement:
        raw["data"]["attributes"]["visitor_statement"] = statement
    return raw


def test_verified_claim_with_matching_window(db):
    db.add_expected_context("ding", "pharmacy refill", "2026-09-15T09:00:00Z", "2026-09-15T11:00:00Z")
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(_raw(hint="pharmacy")))
    assert ok is True
    assert result.claimed_identity == "pharmacy"
    assert result.verification_status == "verified"
    assert result.risk_level == "low"
    assert result.challenge_question_en == ""
    assert result.caption_en == "Medicine delivery matches your schedule."
    assert result.suggested_replies == ["leave_at_door", "coming", "not_now"]


def test_unverified_high_stakes_police_without_evidence(db):
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(_raw(hint="police")))
    assert ok is True
    assert result.claimed_identity == "police"
    assert result.verification_status == "unverified"
    assert result.risk_level == "high"
    assert "Do not open" in result.challenge_question_en
    assert "Đừng mở cửa" in result.challenge_question_vi
    assert result.caption_en == "Visitor claims to be police. Not verified."
    assert result.caption_vi == "Khách nói là công an. Chưa xác minh."


def test_unverified_medium_package_without_evidence(db):
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(_raw(hint="package")))
    assert ok is True
    assert result.claimed_identity == "package"
    assert result.verification_status == "unverified"
    assert result.risk_level == "medium"
    assert result.challenge_question_en != ""


def test_snapshot_alone_does_not_verify_a_claim(db):
    raw = _raw(hint="police")
    raw["snapshot_url"] = "https://example.invalid/frame.jpg"
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(raw))
    assert ok is True
    assert result.verification_status == "unverified"
    assert result.risk_level == "high"


def test_previous_user_label_does_not_verify_a_claim(db):
    prior_id = db.insert_event("ring", "front_door", "ding", "2026-09-15T09:00:00Z", {"meta": {}})
    db.add_label(prior_id, "device:front_door", "police", "pwa")
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(_raw(hint="police")))
    assert ok is True
    assert result.verification_status == "unverified"
    assert result.risk_level == "high"


def test_visitor_statement_is_detected_as_a_claim(db):
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(
        _event(_raw(statement="I am a police officer. Please open the door."))
    )
    assert ok is True
    assert result.claimed_identity == "police"
    assert result.verification_status == "unverified"
    assert result.risk_level == "high"
    assert "Do not open" in result.challenge_question_en
    assert result.suggested_replies == ["not_now"]


def test_authority_claim_vs_different_expected_window_is_contradiction(db):
    db.add_expected_context("ding", "family visit", "2026-09-15T09:00:00Z", "2026-09-15T11:00:00Z")
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(_raw(hint="police")))
    assert ok is True
    assert result.claimed_identity == "police"
    assert result.verification_status == "contradiction"
    assert result.risk_level == "high"
    assert result.challenge_question_en != ""


def test_unexpected_delivery_is_unverified_not_contradiction(db):
    db.add_expected_context("ding", "family visit", "2026-09-15T09:00:00Z", "2026-09-15T11:00:00Z")
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(_raw(hint="pharmacy")))
    assert ok is True
    assert result.claimed_identity == "pharmacy"
    assert result.verification_status == "unverified"
    assert result.risk_level == "high"


def test_no_claim_leaves_existing_behavior_unchanged(db):
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event(_raw()))
    assert ok is True
    assert result.claimed_identity == ""
    assert result.verification_status == "no_claim"
    assert result.risk_level == "low"
    assert result.challenge_question_en == ""
    assert result.category.value == "UNKNOWN_VISITOR"


def test_mcp_detail_surfaces_verification_memory_and_turns(db):
    from backend.config import Settings
    from backend.mcp_server import MCPServer

    event_id = db.insert_event("ring", "front_door", "ding", "2026-09-15T10:00:00Z", {"meta": {}})
    db.update_triage(
        event_id,
        {"category": "MED_DELIVERY", "urgency": 8, "confidence": 0.85, "evidence": ["doorbell"],
         "caption_en": "Possible prescription delivery", "caption_vi": "",
         "verification_status": "unverified", "risk_level": "high",
         "claimed_identity": "pharmacy", "challenge_question_en": "Ask for order number.",
         "challenge_question_vi": "Hỏi mã đơn hàng.", "memory_action": "leave_at_door",
         "memory_basis_en": "Last time for medicine delivery you chose: Leave package.",
         "memory_basis_vi": "Lần trước với giao thuốc bạn đã chọn: Để gói hàng ở cửa."},
        status="enriched",
    )
    db.add_door_turn(event_id, "visitor", "Who are you?", "en")
    server = MCPServer(db, Settings())
    detail = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": "get_event_detail", "arguments": {"event_id": event_id}}}
    )
    import json as _json

    payload = _json.loads(detail["result"]["content"][0]["text"])
    assert payload["verification_status"] == "unverified"
    assert payload["risk_level"] == "high"
    assert payload["claimed_identity"] == "pharmacy"
    assert payload["memory_action"] == "leave_at_door"
    assert payload["door_turns"][0]["text"] == "Who are you?"
