import json
import logging

from .metrics import metrics

logger = logging.getLogger("accessbell.aws")


class EventPublisher:
    def __init__(self, settings, client=None):
        self._settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self._settings.eventbridge_bus_name)

    def _client_or_create(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("events", region_name=self._settings.aws_region)
        return self._client

    def build_entry(self, event: dict, triage: dict) -> dict:
        detail = {
            "event_id": event.get("id"),
            "device_id": event.get("device_id"),
            "kind": event.get("kind"),
            "occurred_at": event.get("occurred_at"),
            "status": event.get("status"),
            "category": triage.get("category"),
            "urgency": triage.get("urgency"),
            "confidence": triage.get("confidence"),
            "grounding": triage.get("grounding"),
            "verification_status": triage.get("verification_status"),
            "risk_level": triage.get("risk_level"),
        }
        return {
            "Source": "accessbell.door",
            "DetailType": "DoorEventTriaged",
            "Detail": json.dumps(detail, ensure_ascii=False),
            "EventBusName": self._settings.eventbridge_bus_name,
        }

    def publish(self, event: dict, triage: dict) -> bool:
        if not self.enabled:
            return False
        try:
            client = self._client_or_create()
            client.put_events(Entries=[self.build_entry(event, triage)])
            metrics.increment("eventbridge_published")
            return True
        except Exception:
            metrics.increment("eventbridge_failed")
            logger.exception("eventbridge publish failed")
            return False
