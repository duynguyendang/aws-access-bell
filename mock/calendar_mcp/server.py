import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from uuid import uuid4

PROTOCOL_VERSION = "2025-11-25"

DEMO_EVENTS = [
    {
        "title": "Pharmacy delivery",
        "start": "2026-09-15T09:00:00Z",
        "end": "2026-09-15T10:30:00Z",
    },
]

TOOLS = [
    {
        "name": "list_events",
        "description": "List calendar events overlapping [start, end).",
        "inputSchema": {
            "type": "object",
            "properties": {"start": {"type": "string"}, "end": {"type": "string"}},
        },
    },
    {
        "name": "create_event",
        "description": "Create a calendar event.",
        "inputSchema": {
            "type": "object",
            "required": ["title", "start", "end"],
            "properties": {
                "title": {"type": "string"},
                "start": {"type": "string"},
                "end": {"type": "string"},
            },
        },
    },
]


class CalendarStore:
    def __init__(self, events=None):
        self._events = [dict(event, id=event.get("id") or f"cal-{uuid4().hex[:8]}") for event in (events or [])]

    def create_event(self, title, start, end):
        event = {
            "id": f"cal-{uuid4().hex[:8]}",
            "title": str(title or ""),
            "start": str(start or ""),
            "end": str(end or ""),
        }
        self._events.append(event)
        return event

    def list_events(self, start: str = "", end: str = "") -> list[dict]:
        out = []
        for event in self._events:
            if start and event["end"] and event["end"] < start:
                continue
            if end and event["start"] and event["start"] > end:
                continue
            out.append(event)
        return out


def _result(request_id, result):
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_rpc(body: dict, store: CalendarStore) -> dict | None:
    method = body.get("method")
    request_id = body.get("id")
    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "calendar-mcp-stub", "version": "0.1.0"},
            },
        )
    if method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})
    if method != "tools/call":
        return _error(request_id, -32601, f"method not found: {method}")
    params = body.get("params") or {}
    name = params.get("name")
    args = params.get("arguments") or {}
    if name == "list_events":
        data = {"events": store.list_events(args.get("start", ""), args.get("end", ""))}
    elif name == "create_event":
        if not args.get("title"):
            return _error(request_id, -32602, "title required")
        data = store.create_event(args.get("title"), args.get("start"), args.get("end"))
    else:
        return _error(request_id, -32602, f"unknown tool: {name}")
    return _result(request_id, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]})


class CalendarHandler(BaseHTTPRequestHandler):
    store = CalendarStore(DEMO_EVENTS)

    def do_POST(self):
        if self.path not in ("/mcp", "/"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.send_error(400)
            return
        response = handle_rpc(body, self.store)
        if response is None:
            self.send_response(202)
            self.end_headers()
            return
        data = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        return


def main():
    port = int(os.getenv("PORT", "8085"))
    server = HTTPServer(("0.0.0.0", port), CalendarHandler)
    print(f"Calendar MCP stub listening on http://localhost:{port}/mcp")
    server.serve_forever()


if __name__ == "__main__":
    main()