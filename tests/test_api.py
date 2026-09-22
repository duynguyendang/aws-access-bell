import json
import os
import time
import uuid

if "DB_URL" not in os.environ:
    os.environ["DB_URL"] = f"sqlite:////tmp/accessbell_api_{uuid.uuid4().hex}.db"
os.environ["LLM_PROVIDER"] = "stub"
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"
os.environ["DEMO_TOKEN"] = ""

import hmac
import hashlib

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.config import settings

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture(scope="module")
def client():
    with TestClient(main_module.app) as test_client:
        yield test_client


def wait_for_enriched(client, event_id, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        event = client.get("/api/events?limit=50").json()["events"]
        match = [e for e in event if e["id"] == event_id]
        if match and match[0]["status"] in {"enriched", "enrichment_failed"}:
            return match[0]
        time.sleep(0.1)
    raise AssertionError(f"event {event_id} never enriched")


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["llm_provider"] == "stub"


def test_settings_reads_port_env(monkeypatch):
    monkeypatch.setenv("PORT", "9099")
    from backend.config import Settings

    assert Settings().port == 9099


def test_simulate_creates_raw_then_enriched(client):
    resp = client.post("/api/simulate?fixture=doorbell_med")
    assert resp.status_code == 200
    event_id = resp.json()["event_id"]
    enriched = wait_for_enriched(client, event_id)
    assert enriched["triage"]["category"] == "MED_DELIVERY"
    assert enriched["triage"]["caption_vi"]


def test_simulate_unknown_fixture_404(client):
    assert client.post("/api/simulate?fixture=does_not_exist").status_code == 404


def test_webhook_ingest_and_debounce(client):
    payload = {"kind": "ding", "device_id": "back_door", "occurred_at": "2026-09-15T08:00:00Z"}
    first = client.post("/webhooks/ring", json=payload)
    assert first.status_code == 200
    assert first.json()["deduped"] is False
    dup = client.post("/webhooks/ring", json={**payload, "occurred_at": "2026-09-15T08:00:03Z"})
    assert dup.json()["deduped"] is True
    assert dup.json()["event_id"] == first.json()["event_id"]


def test_webhook_invalid_json_400(client):
    resp = client.post("/webhooks/ring", content=b"not-json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400


def test_webhook_accepts_partner_v11_envelope(client):
    payload = {
        "meta": {
            "version": "1.1",
            "time": "2026-09-15T14:00:00Z",
            "request_id": "api-v11-1",
            "account_id": "acct-api",
        },
        "data": {
            "id": "v11_door_button_press_1789480800000",
            "type": "button_press",
            "attributes": {"source": "v11_door", "source_type": "devices", "timestamp": 1789480800000},
        },
    }
    first = client.post("/webhooks/ring", json=payload)
    assert first.status_code == 200
    assert first.json()["deduped"] is False
    retry = client.post("/webhooks/ring", json={**payload, "meta": {**payload["meta"], "request_id": "api-v11-1"}})
    assert retry.json()["deduped"] is True
    assert retry.json()["event_id"] == first.json()["event_id"]


def test_webhook_accepts_x_ring_signature_alias(client, monkeypatch):
    monkeypatch.setattr(settings, "ring_webhook_enabled", True)
    monkeypatch.setattr(settings, "ring_secret", "alias-secret")
    payload = b'{"kind":"ding","device_id":"alias_door","occurred_at":"2026-09-15T06:00:00Z"}'
    good = hmac.new(b"alias-secret", payload, hashlib.sha256).hexdigest()
    ok = client.post("/webhooks/ring", content=payload, headers={"X-Ring-Signature": good})
    assert ok.status_code == 200


def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr(settings, "ring_webhook_enabled", True)
    monkeypatch.setattr(settings, "ring_secret", "s3cret")
    payload = b'{"kind":"ding","device_id":"front_door","occurred_at":"2026-09-15T07:00:00Z"}'
    assert client.post("/webhooks/ring", content=payload).status_code == 401
    good = hmac.new(b"s3cret", payload, hashlib.sha256).hexdigest()
    ok = client.post("/webhooks/ring", content=payload, headers={settings.ring_signature_header: good})
    assert ok.status_code == 200


def test_quick_reply_flow(client):
    event_id = client.post("/api/simulate?fixture=doorbell_unknown").json()["event_id"]
    bad = client.post(f"/api/events/{event_id}/reply", json={"action": "fly_away"})
    assert bad.status_code == 400
    ok = client.post(f"/api/events/{event_id}/reply", json={"action": "coming"})
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    child = client.post(f"/api/events/{event_id}/reply", json={"action": "waiting_for_parent"})
    assert child.status_code == 200
    assert client.post("/api/events/999999/reply", json={"action": "coming"}).status_code == 404


def test_event_read_back_matches_write(client):
    event_id = client.post("/api/simulate?fixture=motion_only").json()["event_id"]
    wait_for_enriched(client, event_id)
    event = client.get(f"/api/events/{event_id}").json()
    assert event["id"] == event_id
    assert event["triage"]["category"] == "MOTION_ANOMALY"
    assert event["why"]["en"]
    assert client.get("/api/events/999999").status_code == 404


def test_confirm_adds_ground_truth_label(client):
    event_id = client.post("/api/simulate?fixture=motion_night").json()["event_id"]
    assert client.post(f"/api/events/{event_id}/confirm", json={"label": "wind blew a bag"}).status_code == 200
    assert client.post(f"/api/events/{event_id}/confirm", json={"label": "  "}).status_code == 400


def test_brief_counts_events_on_fixture_date(client):
    client.post("/api/simulate?fixture=doorbell_med")
    brief = client.get("/api/brief?date=2026-09-15").json()
    assert brief["total"] >= 1
    assert brief["by_category"]["MED_DELIVERY"] >= 1
    assert isinstance(brief["bullets"], list) and brief["bullets"]
    vi = client.get("/api/brief?date=2026-09-15&lang=vi").json()
    assert any("Hôm nay" in line or "sự kiện" in line for line in vi["bullets"])


def test_share_requires_consent_and_logs(client):
    denied = client.post("/api/share", json={"consent": False, "recipient": "nurse@example.com"})
    assert denied.status_code == 400
    shared = client.post("/api/share", json={"consent": True, "recipient": "nurse@example.com", "date": "2026-09-15"})
    assert shared.status_code == 200
    body = shared.json()
    assert body["ok"] is True and body["share_id"] >= 1
    assert "AccessBell daily brief" in body["message"]
    assert main_module.db.list_events(since="2026-09-15T00:00:00Z", until="2026-09-15T23:59:59Z", limit=500)


def test_expected_list_and_delete(client):
    created = client.post(
        "/api/expected",
        json={
            "kind": "ding",
            "label": "pharmacy",
            "window_start": "2026-09-15T09:00:00Z",
            "window_end": "2026-09-15T10:30:00Z",
        },
    ).json()
    windows = client.get("/api/expected").json()["windows"]
    assert any(window["id"] == created["id"] for window in windows)
    assert client.delete(f"/api/expected/{created['id']}").json()["removed"] == created["id"]
    assert client.delete(f"/api/expected/{created['id']}").status_code == 404


def test_share_preview_log_and_revoke(client):
    preview = client.post(
        "/api/share/preview",
        json={"consent": False, "recipient": "nurse@example.com", "date": "2026-09-15"},
    )
    assert preview.status_code == 200
    assert preview.json()["requires_consent"] is True
    shared = client.post(
        "/api/share", json={"consent": True, "recipient": "nurse@example.com", "date": "2026-09-15"}
    ).json()
    log = client.get("/api/share/log").json()["log"]
    assert any(row["id"] == shared["share_id"] for row in log)
    revoked = client.post(f"/api/share/{shared['share_id']}/revoke").json()
    assert revoked["ok"] is True and revoked["revoked"] == shared["share_id"]
    assert client.post("/api/share/999999/revoke").status_code == 404


def test_api_auth_gate_when_enabled(client, monkeypatch):
    monkeypatch.setattr(settings, "api_auth_disabled", False)
    monkeypatch.setattr(settings, "api_token", "s3cret")
    assert client.get("/api/events").status_code == 401
    assert client.get("/api/events", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    assert client.get("/api/events?token=s3cret").status_code == 200
    assert client.get("/api/events", cookies={"accessbell_token": "s3cret"}).status_code == 200
    assert client.get("/health").status_code == 200
    monkeypatch.setattr(settings, "api_auth_disabled", True)


def test_pwa_assets_and_index_reference(client):
    manifest = client.get("/assets/manifest.json")
    assert manifest.status_code == 200
    assert manifest.json()["icons"]
    assert client.get("/assets/icon.svg").status_code == 200
    page = client.get("/").text
    assert "manifest.json" in page
    assert "sr-live" in page


def test_escalation_stop_endpoint(client):
    event_id = client.post("/api/simulate?fixture=doorbell_med").json()["event_id"]
    stopped = client.post("/api/escalation/stop", json={"event_id": event_id, "source": "pwa"})
    assert stopped.status_code == 200
    assert stopped.json()["ok"] is True
    assert client.post("/api/escalation/stop", json={"event_id": 999999}).status_code == 404


def test_advisor_suggests_without_writing(client):
    for _ in range(2):
        event_id = main_module.db.insert_event(
            "mock", "advisor_door", "ding", "2026-09-15T10:20:00Z", {"meta": {}}
        )
        main_module.db.update_triage(
            event_id,
            {"category": "UNKNOWN_VISITOR", "grounding": "demoted_insufficient_evidence", "urgency": 4},
        )
    advise = client.get("/api/advise").json()
    assert advise["read_only"] is True and advise["auto_write"] is False
    assert advise["demoted_total"] >= 2
    assert any(item["kind"] == "expected_window" for item in advise["suggestions"])
    assert all(item["auto_write"] is False for item in advise["suggestions"])


def test_ui_strings_and_advisor_endpoints(client):
    strings = client.get("/api/ui-strings?lang=vi").json()
    assert strings["language"] == "vi"
    assert strings["strings"]["stop_escalation"]
    advise = client.get("/api/advise").json()
    assert advise["read_only"] is True and advise["auto_write"] is False
    assert isinstance(advise["suggestions"], list)


def test_policy_and_metrics_endpoints(client):
    policy = client.get("/api/policy").json()
    assert policy["version"] == "1"
    assert len(policy["sha256"]) == 64
    metrics = client.get("/api/metrics").json()
    assert metrics["source"].startswith("fixture-derived")
    assert set(metrics["grounding"]) == {"grounded", "generic", "demoted_insufficient_evidence"}
    assert isinstance(metrics["timers"], dict)
    assert metrics["policy"]["sha256"] == policy["sha256"]


def test_event_serialization_includes_why_and_child(client):
    event_id = client.post("/api/simulate?fixture=doorbell_unknown").json()["event_id"]
    wait_for_enriched(client, event_id)
    events = client.get("/api/events?limit=50").json()["events"]
    match = next(event for event in events if event["id"] == event_id)
    assert match["why"]["en"] and match["why"]["vi"]
    assert match["caption_child"]["en"] and match["caption_child"]["vi"]
    assert match["triage"]["context_status"] == "disabled"


def test_prefs_roundtrip_and_validation(client):
    default = client.get("/api/prefs").json()
    assert default["mode"] in {"caption", "voice", "both"}
    assert client.post("/api/prefs", json={"mode": "caption", "language": "vi"}).status_code == 200
    assert client.get("/api/prefs").json() == {"mode": "caption", "language": "vi"}
    assert client.post("/api/prefs", json={"mode": "telepathy", "language": "en"}).status_code == 400


def test_mcp_endpoint_requires_bearer_token(client, monkeypatch):
    monkeypatch.setattr(settings, "mcp_http_token", "tok123")
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    assert client.post("/mcp", json=body).status_code == 401
    ok = client.post("/mcp", json=body, headers={"Authorization": "Bearer tok123"})
    assert ok.status_code == 200
    assert len(ok.json()["result"]["tools"]) == 11
    monkeypatch.setattr(settings, "mcp_http_token", "")


def test_mcp_401_www_authenticate_toggle(client, monkeypatch):
    monkeypatch.setattr(settings, "mcp_http_token", "tok401")
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    monkeypatch.setattr(settings, "mcp_401_www_authenticate", True)
    challenge = client.post("/mcp", json=body)
    assert challenge.status_code == 401
    assert "www-authenticate" in {key.lower() for key in challenge.headers}
    monkeypatch.setattr(settings, "mcp_401_www_authenticate", False)
    bare = client.post("/mcp", json=body)
    assert bare.status_code == 401
    assert "www-authenticate" not in {key.lower() for key in bare.headers}
    monkeypatch.setattr(settings, "mcp_http_token", "")


def test_mcp_endpoint_rejects_non_object_and_bad_origin(client, monkeypatch):
    assert client.post("/mcp", json=[1, 2]).status_code == 400
    monkeypatch.setattr(settings, "mcp_origin", "https://client.example.com")
    denied = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={"Origin": "https://evil.test"})
    assert denied.status_code == 403
    allowed = client.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}, headers={"Origin": "https://client.example.com"}
    )
    assert allowed.status_code == 200
    monkeypatch.setattr(settings, "mcp_origin", "")


def test_stream_broker_publish_format():
    broker = main_module.StreamBroker()
    queue = broker.subscribe()
    broker.publish({"type": "alert_raw", "event_id": 5, "text": "Someone is at the door"})
    payload = queue.get_nowait()
    assert payload.startswith("data: ")
    assert payload.endswith("\n\n")
    message = json.loads(payload[len("data: ") : -2])
    assert message == {"type": "alert_raw", "event_id": 5, "text": "Someone is at the door"}
    broker.unsubscribe(queue)
    broker.publish({"type": "after_unsubscribe"})
    assert queue.empty()


def test_stream_broker_close_sends_sentinel():
    broker = main_module.StreamBroker()
    queue = broker.subscribe()
    broker.close()
    assert queue.get_nowait() is None


def test_sse_endpoint_registered():
    assert "/api/stream" in main_module.app.openapi()["paths"]
