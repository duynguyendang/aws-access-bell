"""Memory tests: same-as-last-time suggestion only on same-category match."""

import json

from backend.llm.stub import StubLLM
from backend.triage import EnrichmentPipeline


def _seed_prior(db, category="MED_DELIVERY", action="leave_at_door", device="front_door"):
    event_id = db.insert_event("ring", device, "ding", "2026-09-15T08:00:00Z", {"meta": {}})
    db.update_triage(
        event_id,
        {"category": category, "urgency": 8, "confidence": 0.85, "evidence": ["doorbell"],
         "caption_en": "Prior event", "caption_vi": ""},
        status="enriched",
    )
    db.add_label(event_id, f"device:{device}", action, "pwa")
    return event_id


def _event(raw, occurred_at="2026-09-15T10:00:00Z"):
    return dict(
        id=99,
        kind="ding",
        device_id="front_door",
        occurred_at=occurred_at,
        raw_json=json.dumps(raw),
        triage_json="{}",
    )


def test_memory_suggests_last_reply_on_same_category(db):
    _seed_prior(db)
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(
        _event({"meta": {}, "data": {"attributes": {"label_hint": "pharmacy"}}})
    )
    assert ok is True
    assert result.category.value == "MED_DELIVERY"
    assert result.memory_action == "leave_at_door"
    assert "Leave package" in result.memory_basis_en
    assert "Để gói hàng ở cửa" in result.memory_basis_vi


def test_memory_empty_on_different_category(db):
    _seed_prior(db)
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(
        _event({"meta": {}, "data": {"attributes": {"label_hint": "package"}}})
    )
    assert ok is True
    assert result.category.value == "PACKAGE_DELIVERY"
    assert result.memory_action == ""
    assert result.memory_basis_en == ""


def test_memory_empty_without_history(db):
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(
        _event({"meta": {}, "data": {"attributes": {"label_hint": "pharmacy"}}})
    )
    assert ok is True
    assert result.memory_action == ""
