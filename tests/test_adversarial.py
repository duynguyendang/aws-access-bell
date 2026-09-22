import json

from backend.db import Database
from backend.triage import Category, EnrichmentPipeline
from backend.webhook import verify_ring_signature


def test_forged_and_missing_signatures_are_rejected():
    body = b'{"meta":{"request_id":"x"}}'
    assert verify_ring_signature(body, "deadbeef", "secret") is False
    assert verify_ring_signature(body, "", "secret") is False


class InventingLLM:
    name = "inventing"

    def triage(self, **kwargs):
        return {
            "category": "FAMILY_VISITOR",
            "urgency": 3,
            "confidence": 0.95,
            "evidence": ["doorbell"],
            "caption_en": "Your friend Alex is at the door",
            "caption_vi": "",
        }


class ExplodingLLM:
    name = "boom"

    def triage(self, **kwargs):
        raise RuntimeError("model down")


def _event(raw=None):
    return dict(
        id=1,
        kind="ding",
        device_id="d1",
        occurred_at="2026-09-15T10:00:00Z",
        raw_json=json.dumps(raw or {"meta": {}}),
        triage_json="{}",
    )


def test_inventing_llm_is_demoted_with_audit_status(db):
    result, ok = EnrichmentPipeline(db, InventingLLM()).enrich(_event())
    assert ok is True
    assert result.category == Category.UNKNOWN_VISITOR
    assert result.grounding == "demoted_insufficient_evidence"
    assert "Alex" not in result.caption_en


def test_llm_failure_falls_back_to_tier1(db):
    result, ok = EnrichmentPipeline(db, ExplodingLLM()).enrich(_event())
    assert ok is False
    assert result.grounding == "generic"
    assert result.category == Category.UNKNOWN_VISITOR


def test_pending_escalation_claim_is_single_use(tmp_path):
    database = Database(f"sqlite:///{tmp_path / 'claim.db'}")
    database.init_schema()
    database.upsert_pending_escalation(1, "2026-09-15T10:00:00Z", 90)
    assert database.claim_pending_escalation(1) is True
    assert database.claim_pending_escalation(1) is False
    database.close()