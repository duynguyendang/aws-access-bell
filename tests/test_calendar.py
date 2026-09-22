import json

import httpx

from backend.calendar_mcp import CalendarClient, build_calendar_client, parse_tool_result
from backend.config import Settings
from mock.calendar_mcp.server import CalendarStore, handle_rpc


def _call(store, name, arguments):
    return handle_rpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
        store,
    )


def test_calendar_stub_initialize_tools_and_errors():
    store = CalendarStore()
    init = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, store)
    assert init["result"]["protocolVersion"] == "2025-11-25"
    tools = handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, store)
    assert {tool["name"] for tool in tools["result"]["tools"]} == {"list_events", "create_event"}
    assert handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}, store) is None
    assert handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "nope"}, store)["error"]["code"] == -32601
    assert _call(store, "create_event", {})["error"]["code"] == -32602
    assert _call(store, "unknown", {})["error"]["code"] == -32602


def test_calendar_stub_create_and_list_window():
    store = CalendarStore()
    created = _call(
        store,
        "create_event",
        {"title": "Pharmacy delivery", "start": "2026-09-15T09:00:00Z", "end": "2026-09-15T10:30:00Z"},
    )
    assert created["result"]["content"]
    listed = _call(
        store, "list_events", {"start": "2026-09-15T09:45:00Z", "end": "2026-09-15T11:45:00Z"}
    )
    events = json.loads(listed["result"]["content"][0]["text"])["events"]
    assert events[0]["title"] == "Pharmacy delivery"
    outside = _call(store, "list_events", {"start": "2026-09-15T12:00:00Z", "end": "2026-09-15T13:00:00Z"})
    assert json.loads(outside["result"]["content"][0]["text"])["events"] == []


def test_parse_tool_result_shapes():
    body = {"result": {"content": [{"type": "text", "text": json.dumps({"events": [{"title": "x"}]})}]}}
    assert parse_tool_result(body) == [{"title": "x"}]
    assert parse_tool_result({"result": {"content": []}}) == []
    assert parse_tool_result({}) == []
    assert parse_tool_result({"result": {"content": [{"type": "text", "text": "not-json"}]}}) == []


def test_calendar_client_posts_tools_call():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"result": {"content": [{"type": "text", "text": json.dumps({"events": [{"title": "Pharmacy delivery"}]})}]}},
        )

    client = CalendarClient("http://cal.test/mcp", token="tok", transport=httpx.MockTransport(handler))
    events = client.list_events("2026-09-15T09:45:00Z")
    assert events[0]["title"] == "Pharmacy delivery"
    assert captured["payload"]["params"]["name"] == "list_events"
    assert captured["payload"]["params"]["arguments"]["end"] == "2026-09-15T11:45:00Z"
    assert captured["authorization"] == "Bearer tok"
    client.close()


def test_build_calendar_client_respects_env(monkeypatch):
    monkeypatch.setenv("CALENDAR_MCP_URL", "")
    assert build_calendar_client(Settings()) is None
    monkeypatch.setenv("CALENDAR_MCP_URL", "http://cal.test/mcp")
    assert isinstance(build_calendar_client(Settings()), CalendarClient)