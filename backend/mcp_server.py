import json

from .brief import build_daily_summary
from .webhook import extract_payload_hints

PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2025-06-18", "2025-11-25", "2026-07-28")

QUICK_REPLY_ACTIONS = {"leave_at_door", "coming", "not_now", "waiting_for_parent"}
PREFS_MODES = {"caption", "voice", "both"}

TOOLS = [
    {
        "name": "get_door_alerts",
        "description": "List recent door alerts, optionally filtered by time and minimum urgency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "ISO 8601 UTC, e.g. 2026-09-15T00:00:00Z"},
                "urgency_min": {"type": "integer", "minimum": 0, "maximum": 10},
            },
        },
    },
    {
        "name": "get_event_detail",
        "description": "One door alert with full triage, evidence, and user labels.",
        "inputSchema": {
            "type": "object",
            "required": ["event_id"],
            "properties": {"event_id": {"type": "integer"}},
        },
    },
    {
        "name": "get_context_snapshot",
        "description": "Transparency: the local context inputs used for an event (expected windows, labels, payload hints) and whether a calendar join is configured.",
        "inputSchema": {
            "type": "object",
            "required": ["event_id"],
            "properties": {"event_id": {"type": "integer"}},
        },
    },
    {
        "name": "get_daily_summary",
        "description": "Accessible daily brief of door events.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "ISO date YYYY-MM-DD; defaults to today (UTC)"},
                "language": {"type": "string", "enum": ["en", "vi"]},
            },
        },
    },
    {
        "name": "add_expected_context",
        "description": "Record an expected visit window, e.g. pharmacy delivery ~10am.",
        "inputSchema": {
            "type": "object",
            "required": ["kind", "label", "window_start", "window_end"],
            "properties": {
                "kind": {"type": "string"},
                "label": {"type": "string"},
                "window_start": {"type": "string", "description": "ISO 8601 UTC"},
                "window_end": {"type": "string", "description": "ISO 8601 UTC"},
            },
        },
    },
    {
        "name": "list_expected_context",
        "description": "List the door calendar: expected visit windows (door intent).",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 200}},
        },
    },
    {
        "name": "clear_expected_context",
        "description": "Remove an expected visit window by id or label (revoke door intent).",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}, "label": {"type": "string"}},
        },
    },
    {
        "name": "confirm_event",
        "description": "Provide ground-truth label for an event; used to improve future captions.",
        "inputSchema": {
            "type": "object",
            "required": ["event_id", "label"],
            "properties": {"event_id": {"type": "integer"}, "label": {"type": "string"}},
        },
    },
    {
        "name": "send_quick_reply",
        "description": "Dispatch a one-tap reply for an event.",
        "inputSchema": {
            "type": "object",
            "required": ["event_id", "action"],
            "properties": {"event_id": {"type": "integer"}, "action": {"type": "string", "enum": sorted(QUICK_REPLY_ACTIONS)}},
        },
    },
    {
        "name": "update_accessibility_prefs",
        "description": "Set caption vs voice profile and language.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["caption", "voice", "both"]},
                "language": {"type": "string", "enum": ["en", "vi"]},
            },
        },
    },
    {
        "name": "set_escalation",
        "description": "Consent-based safety net: if the resident does not respond to a high-urgency alert within the timeout, notify trusted contacts. Voice example: 'If nobody answers, tell Lan.'",
        "inputSchema": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "contact_label": {"type": "string"},
                "contact_recipient": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 5, "maximum": 3600},
            },
        },
    },
]


class MCPServer:
    def __init__(self, db, settings, escalation=None):
        self._db = db
        self._settings = settings
        self._escalation = escalation

    def handle(self, body: dict) -> dict | None:
        try:
            method = body["method"]
        except KeyError:
            return self._error(body.get("id"), -32600, "missing method")
        request_id = body.get("id")

        if method == "initialize":
            requested = (body.get("params") or {}).get("protocolVersion")
            negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else PROTOCOL_VERSION
            return self._result(
                request_id,
                {
                    "protocolVersion": negotiated,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "accessbell-mcp", "version": "0.1.0"},
                },
            )
        if method in {"notifications/initialized", "notifications/cancelled", "notifications/roots/list_changed"}:
            return None
        if method == "ping":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            return self._call(request_id, body.get("params") or {})
        return self._error(request_id, -32601, f"method not found: {method}")

    def _call(self, request_id, params: dict) -> dict:
        name = params.get("name")
        args = params.get("arguments") or {}
        handlers = {
            "get_door_alerts": self._get_door_alerts,
            "get_event_detail": self._get_event_detail,
            "get_context_snapshot": self._get_context_snapshot,
            "get_daily_summary": self._get_daily_summary,
            "add_expected_context": self._add_expected_context,
            "list_expected_context": self._list_expected_context,
            "clear_expected_context": self._clear_expected_context,
            "confirm_event": self._confirm_event,
            "send_quick_reply": self._send_quick_reply,
            "update_accessibility_prefs": self._update_prefs,
            "set_escalation": self._set_escalation,
        }
        handler = handlers.get(name)
        if handler is None:
            return self._error(request_id, -32602, f"unknown tool: {name}")
        try:
            data = handler(args)
        except (KeyError, ValueError, TypeError) as exc:
            return self._error(request_id, -32602, str(exc))
        return self._result(request_id, {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]})

    def _get_door_alerts(self, args: dict) -> dict:
        since = args.get("since")
        urgency_min = args.get("urgency_min")
        alerts = []
        for event in self._db.list_events(since=since, limit=50):
            triage = json.loads(event.get("triage_json") or "{}")
            urgency = triage.get("urgency") if isinstance(triage, dict) else None
            if urgency_min is not None and (urgency or 0) < urgency_min:
                continue
            alerts.append(self._alert(event, triage))
        return {"alerts": alerts}

    def _get_event_detail(self, args: dict) -> dict:
        event = self._get_event(int(args["event_id"]))
        detail = self._alert(event, json.loads(event.get("triage_json") or "{}"))
        detail["raw"] = json.loads(event.get("raw_json") or "{}")
        detail["labels"] = self._db.labels_for_event(int(args["event_id"]))
        return detail

    def _get_context_snapshot(self, args: dict) -> dict:
        event = self._get_event(int(args["event_id"]))
        try:
            raw = json.loads(event.get("raw_json") or "{}")
        except (TypeError, ValueError):
            raw = {}
        tags, hint = extract_payload_hints(raw)
        return {
            "event_id": event["id"],
            "occurred_at": event.get("occurred_at"),
            "expected_context": self._db.list_active_expected_context(event["occurred_at"]),
            "user_labels": self._db.labels_for_device(event.get("device_id") or ""),
            "payload_tags": tags,
            "payload_label_hint": hint,
            "calendar_configured": bool(self._settings.calendar_mcp_url),
        }

    def _get_daily_summary(self, args: dict) -> dict:
        return build_daily_summary(
            self._db,
            args.get("date") or None,
            args.get("language") or self._db.get_prefs().get("language") or "en",
        )

    def _add_expected_context(self, args: dict) -> dict:
        expected_id = self._db.add_expected_context(
            args["kind"], args["label"], args["window_start"], args["window_end"], source="alexa"
        )
        return {"id": expected_id}

    def _list_expected_context(self, args: dict) -> dict:
        limit = int(args.get("limit") or 100)
        return {"windows": self._db.list_expected_context(max(1, min(limit, 200)))}

    def _clear_expected_context(self, args: dict) -> dict:
        expected_id = args.get("id")
        label = args.get("label")
        if expected_id is None and not label:
            raise ValueError("id or label required")
        removed = self._db.clear_expected_context(
            int(expected_id) if expected_id is not None else None, label
        )
        return {"removed": removed}

    def _confirm_event(self, args: dict) -> dict:
        event = self._get_event(int(args["event_id"]))
        self._db.add_label(event["id"], f"device:{event['device_id']}", args["label"], source="alexa")
        if self._escalation is not None:
            self._escalation.acknowledge(event["id"], "alexa")
        return {"ok": True}

    def _send_quick_reply(self, args: dict) -> dict:
        action = args["action"]
        if action not in QUICK_REPLY_ACTIONS:
            raise ValueError(f"invalid action '{action}'")
        event = self._get_event(int(args["event_id"]))
        self._db.add_label(event["id"], f"device:{event['device_id']}", action, source="alexa")
        if self._escalation is not None:
            self._escalation.acknowledge(event["id"], "alexa")
        return {"ok": True, "dispatched_to": "announce"}

    def _update_prefs(self, args: dict) -> dict:
        mode = args.get("mode") or "both"
        language = args.get("language") or self._db.get_prefs().get("language") or "en"
        if mode not in PREFS_MODES:
            raise ValueError("mode must be one of caption|voice|both")
        self._db.set_prefs(mode, language)
        return {"ok": True}

    def _set_escalation(self, args: dict) -> dict:
        contact_id = None
        if args.get("contact_recipient"):
            label = args.get("contact_label") or args["contact_recipient"]
            contact_id = self._db.add_escalation_contact(label, args["contact_recipient"], channel="mcp")
        timeout = args.get("timeout_seconds")
        if timeout is not None and timeout < 5:
            raise ValueError("timeout_seconds must be >= 5")
        policy = self._db.set_escalation_policy(enabled=args.get("enabled"), timeout_seconds=timeout)
        return {"ok": True, "contact_id": contact_id, "policy": policy}

    def _get_event(self, event_id: int) -> dict:
        event = self._db.get_event(event_id)
        if event is None:
            raise ValueError(f"unknown event_id: {event_id}")
        return event

    @staticmethod
    def _alert(event: dict, triage: dict) -> dict:
        return {
            "event_id": event["id"],
            "kind": event.get("kind"),
            "device_id": event.get("device_id"),
            "occurred_at": event.get("occurred_at"),
            "status": event.get("status"),
            "category": (triage or {}).get("category"),
            "urgency": (triage or {}).get("urgency"),
            "confidence": (triage or {}).get("confidence"),
            "caption_en": (triage or {}).get("caption_en"),
            "caption_vi": (triage or {}).get("caption_vi"),
            "evidence": (triage or {}).get("evidence"),
            "grounding": (triage or {}).get("grounding"),
        }

    @staticmethod
    def _result(request_id, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}