import hashlib
import hmac
import json
from datetime import datetime, timezone

from .db import Database
from .util import now_iso, seconds_between

RING_EVENT_KIND_MAP = {
    "button_press": "ding",
    "ding": "ding",
    "motion_detected": "motion",
    "motion": "motion",
}


class WebhookError(ValueError):
    pass


def verify_ring_signature(payload: bytes, signature: str, secret: str) -> bool:
    if not secret:
        return True
    if not signature:
        return False
    received = signature.strip()
    if received.lower().startswith("sha256="):
        received = received[7:]
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received.lower())


def request_hash(request_id: str) -> str | None:
    if not request_id:
        return None
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def _ms_to_iso(value) -> str:
    try:
        ms = int(value)
    except (TypeError, ValueError):
        return now_iso()
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_payload_hints(raw: dict) -> tuple[list[str], str]:
    if not isinstance(raw, dict):
        return [], ""
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    attributes = data.get("attributes") if isinstance(data.get("attributes"), dict) else {}
    tags = attributes.get("tags") or meta.get("tags") or []
    hint = attributes.get("label_hint") or meta.get("label_hint") or ""
    return [str(tag) for tag in tags], str(hint)


def parse_ring_payload(data: dict) -> dict:
    if not isinstance(data, dict):
        raise WebhookError("expected a JSON object payload")

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    event = data.get("data") if isinstance(data.get("data"), dict) else {}
    attributes = event.get("attributes") if isinstance(event.get("attributes"), dict) else {}

    raw_type = str(event.get("type") or data.get("kind") or data.get("type") or "motion")
    kind = RING_EVENT_KIND_MAP.get(raw_type.lower(), raw_type.lower() or "motion")

    device_id = attributes.get("source") or data.get("device_id") or data.get("device") or "unknown"

    device_time = _ms_to_iso(attributes.get("timestamp")) if attributes.get("timestamp") is not None else ""
    occurred_at = (
        data.get("occurred_at")
        or data.get("created_at")
        or device_time
        or meta.get("time")
        or now_iso()
    )

    request_id = str(meta.get("request_id") or event.get("id") or "")
    return {
        "kind": kind,
        "raw_type": raw_type,
        "device_id": str(device_id),
        "occurred_at": str(occurred_at),
        "request_id": request_id,
        "account_id": str(meta.get("account_id") or ""),
        "raw": data,
    }


class RingWebhookHandler:
    def __init__(self, db: Database, debounce_seconds: int = 10):
        self._db = db
        self._debounce_seconds = max(debounce_seconds, 0)

    def handle(self, payload: bytes) -> tuple[dict, bool]:
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise WebhookError(f"invalid webhook payload: {exc}") from exc

        parsed = parse_ring_payload(data)
        kind = parsed["kind"]
        device_id = parsed["device_id"]
        occurred_at = parsed["occurred_at"]

        event_hash = request_hash(parsed["request_id"])
        if event_hash:
            existing = self._db.get_event_by_hash(event_hash)
            if existing is not None:
                return existing, True

        for recent in self._db.recent_matching(device_id, kind, limit=self._debounce_seconds + 2):
            if seconds_between(recent["occurred_at"], occurred_at) <= self._debounce_seconds:
                return self._db.get_event(recent["id"]), True

        event_id = self._db.insert_event("ring", device_id, kind, occurred_at, data, event_hash=event_hash)
        return self._db.get_event(event_id), False
