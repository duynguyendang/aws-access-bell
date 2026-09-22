import json

import pytest
from pydantic import ValidationError

from backend.llm.stub import StubLLM
from backend.triage import Category, EnrichmentPipeline, Tier1Rules, TriageResult


def test_tier1_ding_maps_to_unknown_visitor():
    result = Tier1Rules().classify("ding")
    assert result.category == Category.UNKNOWN_VISITOR
    assert result.caption_en == "Someone is at the door"


def test_tier1_motion_maps_to_motion_anomaly():
    result = Tier1Rules().classify("motion")
    assert result.category == Category.MOTION_ANOMALY


def test_tier1_button_press_is_doorbell_evidence():
    result = Tier1Rules().classify("button_press")
    assert result.category == Category.UNKNOWN_VISITOR
    assert result.evidence == ["doorbell"]


def test_tier1_motion_detected_is_motion_evidence():
    result = Tier1Rules().classify("motion_detected")
    assert result.category == Category.MOTION_ANOMALY
    assert result.evidence == ["motion"]


def test_triage_validates_confidence_range():
    with pytest.raises(ValidationError):
        TriageResult(
            category=Category.UNKNOWN_VISITOR,
            urgency=4,
            confidence=1.5,
            caption_en="Someone is at the door",
        )


def test_triage_rejects_unknown_evidence_source():
    with pytest.raises(ValidationError):
        TriageResult(
            category=Category.FAMILY_VISITOR,
            urgency=3,
            confidence=0.9,
            evidence=["guessed_face:" + "friend"],
            caption_en="A friend is at the door",
        )


def test_stub_med_delivery_from_tags():
    out = StubLLM().triage(
        kind="ding",
        device_id="d1",
        occurred_at="2026-09-15T09:45:00Z",
        raw={"meta": {"tags": ["pharmacy", "prescription"]}},
        expected=[],
    )
    assert out["category"] == "MED_DELIVERY"
    assert 0 < out["urgency"] <= 10


def test_stub_unknown_when_no_signal():
    out = StubLLM().triage(
        kind="ding",
        device_id="d1",
        occurred_at="2026-09-15T10:00:00Z",
        raw={"meta": {"tags": []}},
        expected=[],
    )
    assert out["category"] == "UNKNOWN_VISITOR"


def test_pipeline_guardrail_forces_generic_caption(db):
    event = dict(
        id=1,
        kind="ding",
        device_id="d1",
        occurred_at="2026-09-15T10:00:00Z",
        raw_json=json.dumps({"meta": {}}),
        triage_json="{}",
    )

    class InventingLLM:
        name = "inventing"

        def triage(self, **kwargs):
            return {
                "category": "FAMILY_VISITOR",
                "urgency": 3,
                "confidence": 0.9,
                "evidence": ["doorbell"],
                "caption_en": "Your friend Alex is at the door",
                "caption_vi": "",
            }

    result, ok = EnrichmentPipeline(db, InventingLLM()).enrich(event)
    assert ok is True
    assert result.category == Category.UNKNOWN_VISITOR
    assert result.grounding == "demoted_insufficient_evidence"
    assert result.caption_en == "Someone is at the door"
    assert result.do_not_invent is True


def _event(occurred_at="2026-09-15T09:45:00Z", raw=None, kind="ding"):
    return dict(
        id=1,
        kind=kind,
        device_id="d1",
        occurred_at=occurred_at,
        raw_json=json.dumps(raw if raw is not None else {"meta": {}}),
        triage_json="{}",
    )


def test_pipeline_marks_grounded_with_expected_context(db):
    db.add_expected_context("ding", "pharmacy refill", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z")
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event())
    assert ok is True
    assert result.category == Category.MED_DELIVERY
    assert result.grounding == "grounded"


def test_pipeline_marks_generic_without_signal(db):
    result, ok = EnrichmentPipeline(db, StubLLM()).enrich(_event())
    assert ok is True
    assert result.category == Category.UNKNOWN_VISITOR
    assert result.grounding == "generic"


class FakeCalendar:
    def __init__(self, events):
        self._events = events

    def list_events(self, occurred_at):
        return self._events


def test_pipeline_calendar_evidence_grounds(db):
    calendar = FakeCalendar([{"title": "Pharmacy delivery", "start": "2026-09-15T09:00:00Z", "end": "2026-09-15T10:30:00Z"}])
    result, ok = EnrichmentPipeline(db, StubLLM(), calendar=calendar).enrich(_event())
    assert ok is True
    assert result.category == Category.MED_DELIVERY
    assert any(item.startswith("calendar") for item in result.evidence)
    assert result.grounding == "grounded"


def test_quiet_hours_rephrase_night_motion(db):
    pipeline = EnrichmentPipeline(db, StubLLM(), quiet_hours=("22:00", "07:00"))
    result, ok = pipeline.enrich(_event(occurred_at="2026-09-15T02:14:00Z", kind="motion"))
    assert ok is True
    assert result.category == Category.MOTION_ANOMALY
    assert "Quiet hours" in result.caption_en


def test_quiet_hours_do_not_change_daytime_motion(db):
    pipeline = EnrichmentPipeline(db, StubLLM(), quiet_hours=("22:00", "07:00"))
    result, _ = pipeline.enrich(_event(occurred_at="2026-09-15T12:00:00Z", kind="motion"))
    assert "Quiet hours" not in result.caption_en