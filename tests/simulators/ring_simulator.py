import asyncio
import hashlib
import hmac
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@dataclass
class RingEvent:
    event_type: str
    device_id: str = "front_door_sim_001"
    snapshot_key: Optional[str] = None
    expected_label: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class RingSimulator:
    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        webhook_path: str = "/webhooks/ring",
        webhook_secret: str = "test_webhook_secret",
    ):
        self.base_url = os.getenv("BASE_URL", base_url).rstrip("/")
        self.webhook_url = f"{self.base_url}{webhook_path}"
        self.webhook_secret = os.getenv("RING_WEBHOOK_SECRET", webhook_secret)
        self.sent_events: list[dict] = []

    def _sign_payload(self, payload_bytes: bytes) -> str:
        return hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    def _build_payload(self, event: RingEvent) -> dict:
        event_id = f"evt_sim_{uuid.uuid4().hex[:12]}"
        snapshot_url = None
        if event.snapshot_key:
            snapshot_url = f"{self.base_url}/static/test_snapshots/{event.snapshot_key}"

        return {
            "event_id": event_id,
            "event_type": event.event_type,
            "device_id": event.device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_url": snapshot_url,
            "expected_label": event.expected_label,
            "label_hint": event.metadata.get("label_hint") or (event.expected_label or "").lower(),
            "tags": event.metadata.get("tags", []),
            "motion_zones": event.metadata.get("motion_zones", [1]),
            "battery_level": event.metadata.get("battery_level", 85),
            "firmware_version": "sim-1.0.0",
        }

    async def send_event(self, event: RingEvent) -> dict:
        payload = self._build_payload(event)
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._sign_payload(payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "X-Ring-Signature": signature,
            "X-Signature": signature,
            "X-Ring-Event-Type": event.event_type,
        }
        api_token = os.getenv("API_TOKEN", "")
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.webhook_url,
                content=payload_bytes,
                headers=headers,
                timeout=10.0,
            )

        result = {
            "event_id": payload["event_id"],
            "event_type": event.event_type,
            "expected_label": event.expected_label,
            "snapshot_key": event.snapshot_key,
            "http_status": response.status_code,
            "response_body": response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text,
            "sent_at": time.monotonic(),
        }
        self.sent_events.append(result)
        return result

    async def send_doorbell_press(
        self,
        snapshot_key: str,
        expected_label: str,
        device_id: Optional[str] = None,
        **metadata,
    ) -> dict:
        event = RingEvent(
            event_type="doorbell_ding",
            device_id=device_id or f"front_door_sim_{expected_label.lower()}",
            snapshot_key=snapshot_key,
            expected_label=expected_label,
            metadata=metadata,
        )
        return await self.send_event(event)

    async def send_motion(self, snapshot_key: str, device_id: Optional[str] = None, **metadata) -> dict:
        event = RingEvent(
            event_type="motion_detected",
            device_id=device_id or "front_door_sim_motion",
            snapshot_key=snapshot_key,
            expected_label="MOTION_ANOMALY",
            metadata=metadata,
        )
        return await self.send_event(event)

    async def send_debounce_burst(self, count: int = 3, interval_ms: int = 200, device_id: str = "front_door_sim_debounce"):
        results = []
        for _ in range(count):
            r = await self.send_doorbell_press(
                snapshot_key="package_delivery.jpg",
                expected_label="PACKAGE_DELIVERY",
                device_id=device_id,
            )
            results.append(r)
            await asyncio.sleep(interval_ms / 1000.0)
        return results

    def load_scenario(self, scenario_name: str) -> RingEvent:
        path = FIXTURES_DIR / "events" / f"{scenario_name}.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return RingEvent(**data)


SCENARIOS = {
    "package_delivery": {
        "snapshot_key": "package_delivery.jpg",
        "expected_label": "PACKAGE_DELIVERY",
        "urgency": 2,
    },
    "med_delivery": {
        "snapshot_key": "med_delivery.jpg",
        "expected_label": "MED_DELIVERY",
        "urgency": 3,
    },
    "family_visitor": {
        "snapshot_key": "family_visitor.jpg",
        "expected_label": "FAMILY_VISITOR",
        "urgency": 1,
    },
    "unknown_visitor": {
        "snapshot_key": "unknown_visitor.jpg",
        "expected_label": "UNKNOWN_VISITOR",
        "urgency": 2,
    },
    "motion_noise": {
        "snapshot_key": "motion_noise.jpg",
        "expected_label": "MOTION_ANOMALY",
        "urgency": 0,
    },
}


async def run_all_scenarios(base_url: str = "http://localhost:8000"):
    sim = RingSimulator(base_url=base_url)
    results = []
    for name, cfg in SCENARIOS.items():
        print(f"\n▶ Sending scenario: {name}")
        result = await sim.send_doorbell_press(
            snapshot_key=cfg["snapshot_key"],
            expected_label=cfg["expected_label"],
        )
        results.append(result)
        print(f"  HTTP {result['http_status']} | event_id={result['event_id']}")
        await asyncio.sleep(3)
    return results


if __name__ == "__main__":
    asyncio.run(run_all_scenarios())
