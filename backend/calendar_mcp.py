import json
from datetime import timedelta

import httpx

from .util import parse_iso


def parse_tool_result(body: dict) -> list[dict]:
    if not isinstance(body, dict) or "result" not in body:
        return []
    content = (body.get("result") or {}).get("content") or []
    for item in content:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        try:
            data = json.loads(item.get("text") or "{}")
        except (TypeError, ValueError):
            continue
        events = data.get("events") if isinstance(data, dict) else data
        if isinstance(events, list):
            return [event for event in events if isinstance(event, dict)]
    return []


class CalendarClient:
    def __init__(
        self,
        url: str,
        token: str = "",
        timeout: float = 5.0,
        window_seconds: int = 7200,
        transport=None,
    ):
        self._url = url
        self._token = token
        self._timeout = timeout
        self._window = window_seconds
        self._http = httpx.Client(timeout=timeout, transport=transport)

    def _window_end(self, occurred_at: str) -> str:
        try:
            return (parse_iso(occurred_at) + timedelta(seconds=self._window)).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            return occurred_at

    def list_events(self, occurred_at: str) -> list[dict]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "list_events",
                "arguments": {"start": occurred_at, "end": self._window_end(occurred_at)},
            },
        }
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        response = self._http.post(self._url, json=payload, headers=headers)
        response.raise_for_status()
        return parse_tool_result(response.json())

    def close(self):
        self._http.close()


def build_calendar_client(settings):
    if not settings.calendar_mcp_url:
        return None
    budget = max(int(getattr(settings, "context_budget_ms", 200) or 200), 1)
    return CalendarClient(settings.calendar_mcp_url, settings.calendar_mcp_token, timeout=budget / 1000.0)