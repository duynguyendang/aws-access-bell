import hashlib
import hmac
import json
from pathlib import Path

import pytest

from backend.webhook import (
    RingWebhookHandler,
    WebhookError,
    extract_payload_hints,
    parse_ring_payload,
    request_hash,
    verify_ring_signature,
)

SECRET = "super-secret"


def _sig(payload: bytes) -> str:
    return hmac.new(SECRET.encode(), payload, hashlib.sha256).hexdigest()


def _v11(event_type="button_press", request_id="req-1", timestamp=1789466400000, **attributes):
    return {
        "meta": {"version": "1.1", "time": "2026-09-15T10:00:00Z", "request_id": request_id, "account_id": "acct-1"},
        "data": {
            "id": f"ring_doorbell_01_{event_type}_{timestamp}",
            "type": event_type,
            "attributes": {"source": "ring_doorbell_01", "source_type": "devices", "timestamp": timestamp, **attributes},
        },
    }


def test_signature_validates():
    payload = b'{"kind":"ding"}'
    assert verify_ring_signature(payload, _sig(payload), SECRET) is True


def test_signature_rejects_tampered_payload():
    payload = b'{"kind":"ding"}'
    tampered = b'{"kind":"motion"}'
    assert verify_ring_signature(tampered, _sig(payload), SECRET) is False


def test_empty_secret_allows_unsigned_dev_mode():
    assert verify_ring_signature(b"{}", "", "") is True


def test_handler_creates_event(db):
    handler = RingWebhookHandler(db, debounce_seconds=10)
    payload = json.dumps(
        {"kind": "ding", "device_id": "d1", "occurred_at": "2026-09-15T10:00:00Z"}
    ).encode()
    event, deduped = handler.handle(payload)
    assert event["source"] == "ring"
    assert deduped is False


def test_handler_debounces_duplicate_within_window(db):
    handler = RingWebhookHandler(db, debounce_seconds=10)
    first = json.dumps(
        {"kind": "ding", "device_id": "d1", "occurred_at": "2026-09-15T10:00:00Z"}
    ).encode()
    dup = json.dumps(
        {"kind": "ding", "device_id": "d1", "occurred_at": "2026-09-15T10:00:05Z"}
    ).encode()
    later = json.dumps(
        {"kind": "ding", "device_id": "d1", "occurred_at": "2026-09-15T10:00:20Z"}
    ).encode()
    _, _ = handler.handle(first)
    event, deduped = handler.handle(dup)
    assert deduped is True
    event_late, deduped_late = handler.handle(later)
    assert deduped_late is False


def test_handler_rejects_invalid_json(db):
    handler = RingWebhookHandler(db)
    with pytest.raises(WebhookError):
        handler.handle(b"not-json")


def test_parse_v11_button_press_is_doorbell():
    parsed = parse_ring_payload(_v11())
    assert parsed["kind"] == "ding"
    assert parsed["raw_type"] == "button_press"
    assert parsed["device_id"] == "ring_doorbell_01"
    assert parsed["occurred_at"] == "2026-09-15T10:00:00Z"
    assert parsed["request_id"] == "req-1"
    assert parsed["account_id"] == "acct-1"


def test_parse_v11_motion_detected_is_motion():
    parsed = parse_ring_payload(_v11(event_type="motion_detected", timestamp=1789438440000))
    assert parsed["kind"] == "motion"
    assert parsed["occurred_at"] == "2026-09-15T02:14:00Z"


def test_parse_legacy_fixture_shape_still_supported():
    parsed = parse_ring_payload({"kind": "ding", "device_id": "d1", "occurred_at": "2026-09-15T10:00:00Z"})
    assert parsed["kind"] == "ding"
    assert parsed["device_id"] == "d1"


def test_extract_hints_reads_v11_attributes():
    tags, hint = extract_payload_hints(_v11(tags=["pharmacy", "medicine"], label_hint="doctor_delivery"))
    assert tags == ["pharmacy", "medicine"]
    assert hint == "doctor_delivery"


def test_extract_hints_reads_legacy_meta():
    tags, hint = extract_payload_hints({"meta": {"tags": ["package"], "label_hint": "delivery"}})
    assert tags == ["package"]
    assert hint == "delivery"


def test_signature_accepts_sha256_prefix():
    payload = b'{"kind":"ding"}'
    assert verify_ring_signature(payload, "sha256=" + _sig(payload), SECRET) is True


def test_request_hash_is_stable_and_empty_safe():
    assert request_hash("abc") == request_hash("abc")
    assert request_hash("abc") != request_hash("abd")
    assert request_hash("") is None


def test_db_lookup_by_event_hash(db):
    digest = request_hash("req-db-1")
    event_id = db.insert_event("ring", "d1", "ding", "2026-09-15T10:00:00Z", {}, event_hash=digest)
    assert db.get_event_by_hash(digest)["id"] == event_id
    assert db.get_event_by_hash(request_hash("other")) is None
    assert db.get_event_by_hash("") is None


def test_mock_fixtures_follow_v11_envelope():
    events_dir = Path(__file__).resolve().parents[1] / "mock" / "events"
    fixtures = sorted(events_dir.glob("*.json"))
    assert fixtures, "expected mock fixtures"
    for path in fixtures:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["meta"]["version"] == "1.1", path.name
        assert data["meta"]["request_id"], path.name
        assert data["data"]["type"] in {"button_press", "motion_detected"}, path.name
        assert data["data"]["attributes"]["source"], path.name
        parsed = parse_ring_payload(data)
        assert parsed["kind"] in {"ding", "motion"}, path.name


def test_handler_dedupes_by_request_id_beyond_debounce(db):
    handler = RingWebhookHandler(db, debounce_seconds=10)
    first = json.dumps(_v11(request_id="req-abc", timestamp=1789466400000)).encode()
    event, deduped = handler.handle(first)
    assert deduped is False
    retry = json.dumps(_v11(request_id="req-abc", timestamp=1789492800000)).encode()
    again, deduped_again = handler.handle(retry)
    assert deduped_again is True
    assert again["id"] == event["id"]