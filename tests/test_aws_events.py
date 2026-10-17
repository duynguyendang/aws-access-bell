import json
from types import SimpleNamespace

from backend.aws_events import EventPublisher


class FakeClient:
    def __init__(self, error=None):
        self.entries = []
        self._error = error

    def put_events(self, Entries):
        if self._error:
            raise self._error
        self.entries.extend(Entries)
        return {"FailedEntryCount": 0}


def _settings(bus=""):
    return SimpleNamespace(eventbridge_bus_name=bus, aws_region="us-east-1")


def _event():
    return {
        "id": 7,
        "device_id": "d1",
        "kind": "ding",
        "occurred_at": "2026-09-15T10:00:00Z",
        "status": "enriched",
    }


def _triage():
    return {
        "category": "VISITOR",
        "urgency": 6,
        "confidence": 0.9,
        "grounding": "grounded",
        "verification_status": "unverified",
        "risk_level": "medium",
    }


def test_publisher_disabled_without_bus_name():
    client = FakeClient()
    publisher = EventPublisher(_settings(), client=client)
    assert publisher.enabled is False
    assert publisher.publish(_event(), _triage()) is False
    assert client.entries == []


def test_publisher_sends_triaged_entry():
    client = FakeClient()
    publisher = EventPublisher(_settings("accessbell"), client=client)
    assert publisher.publish(_event(), _triage()) is True
    entry = client.entries[0]
    assert entry["Source"] == "accessbell.door"
    assert entry["DetailType"] == "DoorEventTriaged"
    assert entry["EventBusName"] == "accessbell"
    detail = json.loads(entry["Detail"])
    assert detail["event_id"] == 7
    assert detail["category"] == "VISITOR"
    assert detail["verification_status"] == "unverified"
    assert detail["risk_level"] == "medium"


def test_publisher_never_raises_on_aws_failure():
    client = FakeClient(error=RuntimeError("boom"))
    publisher = EventPublisher(_settings("accessbell"), client=client)
    assert publisher.publish(_event(), _triage()) is False
