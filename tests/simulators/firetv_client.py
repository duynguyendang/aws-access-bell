import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class FireTVAlert:
    event_id: str
    alert_type: str
    label: str
    urgency: int
    message: str
    color: str
    timestamp: float
    latency_ms: float = 0.0
    internal_event_id: Optional[str] = None


class FireTVSimulator:
    def __init__(self, base_url: str = "http://localhost:8000"):
        resolved_base = os.getenv("BASE_URL", base_url).rstrip("/")
        self.sse_url = f"{resolved_base}/api/events/stream"
        self.alerts: list[FireTVAlert] = []
        self.connected = False
        self._receive_task: Optional[asyncio.Task] = None

    async def connect(self):
        self._receive_task = asyncio.create_task(self._listen())
        for _ in range(30):
            if self.connected:
                break
            await asyncio.sleep(0.1)

    async def _listen(self):
        headers = {}
        api_token = os.getenv("API_TOKEN", "")
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", self.sse_url, headers=headers) as response:
                    self.connected = True
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            self._parse_sse_event(event_str)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            print(f"SSE listen error: {exc}")
        finally:
            self.connected = False

    def _parse_sse_event(self, event_str: str):
        data_line = None
        for line in event_str.split("\n"):
            if line.startswith("data: "):
                data_line = line[6:]
                break

        if not data_line:
            return

        try:
            data = json.loads(data_line)
        except json.JSONDecodeError:
            return

        alert_type = data.get("alert_type") or ("tier1_raw" if data.get("type") == "alert_raw" else "tier2_enriched")
        label = data.get("label") or data.get("category") or "UNKNOWN"
        urgency = data.get("urgency", 0)
        message = data.get("message") or data.get("text") or ""
        color = data.get("color") or ("red" if urgency >= 3 else ("amber" if urgency >= 2 else "green"))

        alert = FireTVAlert(
            event_id=str(data.get("event_id", "unknown")),
            alert_type=alert_type,
            label=label,
            urgency=urgency,
            message=message,
            color=color,
            timestamp=time.monotonic(),
            internal_event_id=str(data.get("internal_event_id")) if data.get("internal_event_id") is not None else None,
        )

        if "latency_ms" in data:
            alert.latency_ms = float(data["latency_ms"])

        self.alerts.append(alert)
        self._render(alert)

    def _render(self, alert: FireTVAlert):
        color_map = {
            "green": "\033[92m",
            "yellow": "\033[93m",
            "amber": "\033[33m",
            "orange": "\033[33m",
            "red": "\033[91m",
            "white": "\033[97m",
        }
        reset = "\033[0m"
        color = color_map.get(alert.color, "")

        print(f"\n{'='*60}")
        print(f"{color}TV ALERT [{alert.alert_type}]{reset}")
        print(f"{color}   Label:    {alert.label}{reset}")
        print(f"{color}   Urgency:  {'*' * alert.urgency} ({alert.urgency}/3){reset}")
        print(f"{color}   Message:  {alert.message}{reset}")
        if alert.latency_ms > 0:
            print(f"   Latency:  {alert.latency_ms:.0f}ms")
        print(f"{'='*60}")

    def wait_for_alert(self, event_id: str, timeout_s: float = 10.0) -> Optional[FireTVAlert]:
        deadline = time.monotonic() + timeout_s
        target = str(event_id)
        while time.monotonic() < deadline:
            for alert in self.alerts:
                if str(alert.event_id) == target or str(alert.internal_event_id) == target:
                    return alert
            time.sleep(0.1)
        return None

    def get_alerts_for_event(self, event_id: str) -> list[FireTVAlert]:
        target = str(event_id)
        return [a for a in self.alerts if str(a.event_id) == target or str(a.internal_event_id) == target]

    async def disconnect(self):
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        self.connected = False


async def interactive_mode():
    print("AccessBell Fire TV Simulator")
    print("Connecting SSE to backend...")
    sim = FireTVSimulator()
    await sim.connect()

    if not sim.connected:
        print("Could not connect to SSE.")
        return

    print("Connected. Listening for alerts...")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nDisconnecting...")
        await sim.disconnect()


if __name__ == "__main__":
    asyncio.run(interactive_mode())
