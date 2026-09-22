import json

import pytest

from backend.config import Settings
from backend.db import Database
from backend.mcp_server import PROTOCOL_VERSION, MCPServer

TRIAGE = {
    "category": "MED_DELIVERY",
    "urgency": 8,
    "confidence": 0.85,
    "evidence": ["doorbell", "expected_context:pharmacy"],
    "caption_en": "Possible prescription delivery",
    "caption_vi": "Có thể là thuốc ở cửa",
    "suggested_replies": ["leave_at_door", "coming", "not_now"],
    "do_not_invent": True,
}

EXPECTED_TOOLS = {
    "get_door_alerts",
    "get_event_detail",
    "get_context_snapshot",
    "get_daily_summary",
    "add_expected_context",
    "list_expected_context",
    "clear_expected_context",
    "confirm_event",
    "send_quick_reply",
    "update_accessibility_prefs",
    "set_escalation",
}


@pytest.fixture
def mcp(tmp_path):
    database = Database(str(tmp_path / "mcp.db"))
    database.init_schema()
    server = MCPServer(database, Settings())
    yield server, database
    database.close()


def seed_event(database, occurred_at="2026-09-15T09:55:00Z"):
    event_id = database.insert_event("mock", "front_door", "ding", occurred_at, {"meta": {}})
    database.update_triage(event_id, TRIAGE)
    return event_id


def call(server, name, arguments=None):
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments or {}}}
    )
    return response


def call_data(server, name, arguments=None):
    response = call(server, name, arguments)
    assert "error" not in response, response
    return json.loads(response["result"]["content"][0]["text"])


def test_initialize_protocol_version(mcp):
    server, _ = mcp
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION
    assert "tools" in response["result"]["capabilities"]


def test_initialize_negotiates_supported_version(mcp):
    server, _ = mcp
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2026-07-28"}}
    )
    assert response["result"]["protocolVersion"] == "2026-07-28"


def test_initialize_falls_back_on_unknown_version(mcp):
    server, _ = mcp
    response = server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}}
    )
    assert response["result"]["protocolVersion"] == PROTOCOL_VERSION


def test_notifications_return_none(mcp):
    server, _ = mcp
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_unknown_method_jsonrpc_error(mcp):
    server, _ = mcp
    response = server.handle({"jsonrpc": "2.0", "id": 7, "method": "resources/list"})
    assert response["error"]["code"] == -32601


def test_tools_list_matches_readme_catalog(mcp):
    server, _ = mcp
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in response["result"]["tools"]}
    assert names == EXPECTED_TOOLS


def test_get_door_alerts_and_urgency_filter(mcp):
    server, database = mcp
    seed_event(database)
    alerts = call_data(server, "get_door_alerts")["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["category"] == "MED_DELIVERY"
    assert alerts[0]["confidence"] == 0.85
    low = call_data(server, "get_door_alerts", {"urgency_min": 9})["alerts"]
    assert low == []


def test_get_event_detail_includes_evidence_and_labels(mcp):
    server, database = mcp
    event_id = seed_event(database)
    database.add_label(event_id, "device:front_door", "pharmacy", source="alexa")
    detail = call_data(server, "get_event_detail", {"event_id": event_id})
    assert detail["evidence"] == TRIAGE["evidence"]
    assert detail["labels"][0]["label"] == "pharmacy"


def test_get_context_snapshot_is_local_and_read_only(mcp):
    server, database = mcp
    database.add_expected_context("ding", "pharmacy", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z")
    event_id = seed_event(database)
    database.add_label(event_id, "device:front_door", "pharmacy", source="alexa")
    snapshot = call_data(server, "get_context_snapshot", {"event_id": event_id})
    assert snapshot["expected_context"][0]["label"] == "pharmacy"
    assert snapshot["user_labels"][0]["label"] == "pharmacy"
    assert snapshot["calendar_configured"] is False


def test_verify_after_write_on_a_second_surface(mcp):
    server, database = mcp
    event_id = seed_event(database)
    call(server, "confirm_event", {"event_id": event_id, "label": "that was pharmacy"})
    detail = call_data(server, "get_event_detail", {"event_id": event_id})
    assert detail["labels"][0]["label"] == "that was pharmacy"
    call(
        server,
        "add_expected_context",
        {
            "kind": "ding",
            "label": "package",
            "window_start": "2026-09-15T14:00:00Z",
            "window_end": "2026-09-15T16:00:00Z",
        },
    )
    assert call_data(server, "list_expected_context")["windows"][0]["label"] == "package"


def test_get_event_detail_unknown_id(mcp):
    server, _ = mcp
    response = call(server, "get_event_detail", {"event_id": 999})
    assert response["error"]["code"] == -32602


def test_add_expected_context_then_summary(mcp):
    server, database = mcp
    result = call_data(
        server,
        "add_expected_context",
        {
            "kind": "ding",
            "label": "pharmacy refill",
            "window_start": "2026-09-15T09:00:00Z",
            "window_end": "2026-09-15T10:30:00Z",
        },
    )
    assert result["id"] >= 1
    seed_event(database)
    summary = call_data(server, "get_daily_summary", {"date": "2026-09-15"})
    assert summary["total"] == 1
    assert summary["med_deliveries"] == 1
    assert any("medicine" in b or "thuốc" in b for b in summary["bullets"])


def test_list_and_clear_expected_context(mcp):
    server, _ = mcp
    created = call_data(
        server,
        "add_expected_context",
        {
            "kind": "ding",
            "label": "friend visit",
            "window_start": "2026-09-15T15:00:00Z",
            "window_end": "2026-09-15T16:30:00Z",
        },
    )
    windows = call_data(server, "list_expected_context")["windows"]
    assert len(windows) == 1 and windows[0]["label"] == "friend visit"
    cleared = call_data(server, "clear_expected_context", {"id": created["id"]})
    assert cleared["removed"] == 1
    assert call_data(server, "list_expected_context")["windows"] == []
    assert call(server, "clear_expected_context", {})["error"]["code"] == -32602


def test_confirm_event_memory(mcp):
    server, database = mcp
    event_id = seed_event(database)
    assert call(server, "confirm_event", {"event_id": event_id, "label": "that was pharmacy"})["result"]
    labels = database.labels_for_device("front_door")
    assert labels[0]["label"] == "that was pharmacy"


def test_send_quick_reply_valid_and_invalid(mcp):
    server, database = mcp
    event_id = seed_event(database)
    response = call(server, "send_quick_reply", {"event_id": event_id, "action": "leave_at_door"})
    assert json.loads(response["result"]["content"][0]["text"])["ok"] is True
    bad = call(server, "send_quick_reply", {"event_id": event_id, "action": "open_door"})
    assert bad["error"]["code"] == -32602


def test_update_accessibility_prefs(mcp):
    server, database = mcp
    call(server, "update_accessibility_prefs", {"mode": "voice", "language": "vi"})
    assert database.get_prefs() == {"mode": "voice", "language": "vi"}
    bad = call(server, "update_accessibility_prefs", {"mode": "telepathy"})
    assert bad["error"]["code"] == -32602


def test_unknown_tool(mcp):
    server, _ = mcp
    response = call(server, "get_weather")
    assert response["error"]["code"] == -32602
