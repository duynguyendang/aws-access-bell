import hashlib
import hmac
import json
from datetime import datetime, timezone
from uuid import uuid4

DEFAULT_DEMO_SECRET = "accessbell-demo-hmac"

SCENARIOS = {
    "police_claim": {
        "kind": "button_press",
        "label": "Police claim",
        "statement": "I am a police officer. Please open the door.",
    },
    "utility_claim": {
        "kind": "button_press",
        "label": "Utility claim",
        "statement": "I am from the power company. I need to check the meter.",
    },
    "med_delivery": {
        "kind": "button_press",
        "label": "Prescription delivery",
        "statement": "I am delivering your prescription from the pharmacy.",
    },
    "package": {
        "kind": "button_press",
        "label": "Package delivery",
        "statement": "I have a package delivery for you.",
    },
    "family": {
        "kind": "button_press",
        "label": "Family visit",
        "statement": "Hi, it is your family visiting.",
    },
    "unknown": {
        "kind": "button_press",
        "label": "Unknown visitor",
        "statement": "I am looking for someone.",
    },
    "motion": {
        "kind": "motion_detected",
        "label": "Motion only",
        "statement": "",
    },
}


def build_payload(
    scenario: str,
    visitor_statement: str | None = None,
    device_id: str = "ring_doorbell_01",
    occurred_at: datetime | None = None,
) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown Ring scenario: {scenario}")
    spec = SCENARIOS[scenario]
    now = occurred_at or datetime.now(timezone.utc)
    timestamp_ms = int(now.timestamp() * 1000)
    statement = spec["statement"] if visitor_statement is None else visitor_statement
    attributes = {
        "source": device_id,
        "source_type": "devices",
        "timestamp": timestamp_ms,
    }
    if statement:
        attributes["visitor_statement"] = statement
    return {
        "meta": {
            "version": "1.1",
            "time": now.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "request_id": str(uuid4()),
            "account_id": "ava1.ring.account.simulator",
        },
        "data": {
            "id": f"{device_id}_{spec['kind']}_{timestamp_ms}",
            "type": spec["kind"],
            "attributes": attributes,
            "relationships": {
                "devices": {"links": {"self": f"/v1/devices/{device_id}"}}
            },
        },
    }


def sign_payload(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def serialize_payload(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
