import json
import os
import time
import uuid

os.environ.setdefault("LLM_PROVIDER", "stub")
if "DB_URL" not in os.environ:
    os.environ["DB_URL"] = f"sqlite:////tmp/accessbell_esc_{uuid.uuid4().hex}.db"
if "RATE_LIMIT_PER_MINUTE" not in os.environ:
    os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend import main as main_module
from backend.db import Database
from backend.escalation import EscalationManager

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

MED_URGENCY = 8


@pytest.fixture(scope="module")
def client():
    with TestClient(main_module.app) as test_client:
        yield test_client


def simulate(client, fixture="doorbell_med") -> int:
    resp = client.post(f"/api/simulate?fixture={fixture}")
    assert resp.status_code == 200
    return resp.json()["event_id"]


def log_for(client, event_id: int) -> list[dict]:
    rows = client.get("/api/escalation/log").json()["log"]
    return [r for r in rows if r["event_id"] == event_id]


def poll_log(client, event_id: int, status: str, timeout: float = 4.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = [r for r in log_for(client, event_id) if r["status"] == status]
        if rows:
            return rows
        time.sleep(0.1)
    return []


def reset_policy(client, **kwargs):
    client.post("/api/escalation/policy", json=kwargs)


@pytest.fixture(scope="module")
def armed(client):
    reset_policy(client, enabled=False)
    for contact in client.get("/api/escalation/contacts").json()["contacts"]:
        if contact["enabled"]:
            client.delete(f"/api/escalation/contacts/{contact['id']}")
    yield client


def test_default_policy_off(client):
    policy = client.get("/api/escalation/policy").json()
    assert policy["enabled"] is False
    assert policy["timeout_seconds"] == 90
    assert policy["min_urgency"] == 7


def test_disabled_policy_never_escalates(armed):
    reset_policy(armed, enabled=False, timeout_seconds=1, min_urgency=7)
    armed.post("/api/escalation/contacts", json={"label": "con Lan", "recipient": "lan@example.com"})
    event_id = simulate(armed)
    time.sleep(1.6)
    assert log_for(armed, event_id) == []


def test_escalation_fires_after_timeout(armed):
    reset_policy(armed, enabled=True, timeout_seconds=1, min_urgency=7)
    contact = armed.post(
        "/api/escalation/contacts", json={"label": "con Lan", "recipient": "lan@example.com"}
    ).json()
    assert contact["ok"] is True
    event_id = simulate(armed)
    rows = poll_log(armed, event_id, "queued")
    assert rows, "escalation not queued after timeout"
    assert rows[0]["recipient"] == "lan@example.com"
    assert "prescription" in rows[0]["message"].lower() or "pharmacy" in rows[0]["message"].lower()


def test_quick_reply_stops_escalation(armed):
    reset_policy(armed, enabled=True, timeout_seconds=3, min_urgency=7)
    event_id = simulate(armed)
    time.sleep(0.5)
    reply = armed.post(f"/api/events/{event_id}/reply", json={"action": "coming"})
    assert reply.status_code == 200
    stopped = poll_log(armed, event_id, "stopped")
    assert stopped, "expected stopped audit row"
    time.sleep(3.2)
    assert [r for r in log_for(armed, event_id) if r["status"] == "queued"] == []


def test_low_urgency_does_not_escalate(armed):
    reset_policy(armed, enabled=True, timeout_seconds=1, min_urgency=7)
    event_id = simulate(armed, fixture="motion_only")
    time.sleep(1.6)
    assert log_for(armed, event_id) == []


def test_revoked_contacts_get_nothing(armed):
    for contact in armed.get("/api/escalation/contacts").json()["contacts"]:
        if contact["enabled"]:
            assert armed.delete(f"/api/escalation/contacts/{contact['id']}").status_code == 200
    reset_policy(armed, enabled=True, timeout_seconds=1, min_urgency=7)
    event_id = simulate(armed)
    time.sleep(1.6)
    assert log_for(armed, event_id) == []
    assert armed.delete("/api/escalation/contacts/999999").status_code == 404


def test_mcp_set_escalation_tool(armed):
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "set_escalation",
            "arguments": {
                "enabled": True,
                "contact_label": "chau",
                "contact_recipient": "chau@example.com",
                "timeout_seconds": 90,
            },
        },
    }
    response = armed.post("/mcp", json=body)
    data = json.loads(response.json()["result"]["content"][0]["text"])
    assert data["ok"] is True and data["contact_id"] >= 1
    assert data["policy"] == {"enabled": True, "timeout_seconds": 90, "min_urgency": 7}
    bad = armed.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "set_escalation", "arguments": {"timeout_seconds": 1}},
        },
    )
    assert bad.json()["error"]["code"] == -32602
    armed.post("/mcp", json={
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "set_escalation", "arguments": {"enabled": False}},
    })
    assert armed.get("/api/escalation/policy").json()["enabled"] is False


def test_mcp_quick_reply_acknowledges(armed):
    reset_policy(armed, enabled=True, timeout_seconds=3, min_urgency=7)
    contact = armed.post(
        "/api/escalation/contacts", json={"label": "con Lan", "recipient": "lan@example.com"}
    )
    event_id = simulate(armed)
    time.sleep(0.5)
    body = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "send_quick_reply", "arguments": {"event_id": event_id, "action": "coming"}},
    }
    assert armed.post("/mcp", json=body).status_code == 200
    assert poll_log(armed, event_id, "stopped"), "mcp reply should stop escalation"
    reset_policy(armed, enabled=False)
    armed.delete(f"/api/escalation/contacts/{contact.json()['id']}")


class FakeBroker:
    def __init__(self):
        self.messages = []

    def publish(self, message):
        self.messages.append(message)


class FakeNotifier:
    def escalate(self, recipient, message):
        return {"status": "queued", "to": recipient}


def _seed(database, event_id_expected=1):
    database.set_escalation_policy(enabled=True, timeout_seconds=1, min_urgency=7)
    database.add_escalation_contact("con Lan", "lan@example.com")
    event_id = database.insert_event("mock", "d1", "ding", "2026-09-15T09:00:00Z", {})
    database.update_triage(
        event_id,
        {
            "category": "MED_DELIVERY",
            "urgency": 8,
            "confidence": 0.8,
            "evidence": ["doorbell"],
            "caption_en": "Possible prescription delivery",
        },
    )
    return event_id


def test_pending_escalation_survives_restart(tmp_path):
    async def scenario():
        database = Database(f"sqlite:///{tmp_path / 'restart.db'}")
        database.init_schema()
        event_id = _seed(database)

        crashed = EscalationManager(database, FakeBroker(), FakeNotifier())
        assert crashed.schedule(event_id, {"urgency": 8, "caption_en": "Possible prescription delivery"})
        crashed.shutdown()
        assert database.list_pending_escalations(), "pending row must survive a crash"

        revived = EscalationManager(database, FakeBroker(), FakeNotifier())
        assert await revived.recover() == 1
        await asyncio.sleep(1.8)
        rows = [r["status"] for r in database.list_escalation_log() if r["event_id"] == event_id]
        database.close()
        return rows

    assert asyncio.run(scenario()) == ["queued"]


def test_schedule_publishes_armed_before_it_fires(tmp_path):
    async def scenario():
        database = Database(f"sqlite:///{tmp_path / 'armed.db'}")
        database.init_schema()
        event_id = _seed(database)
        broker = FakeBroker()
        manager = EscalationManager(database, broker, FakeNotifier())
        assert manager.schedule(event_id, {"urgency": 8}) is True
        assert broker.messages[0]["type"] == "escalation_armed"
        assert broker.messages[0]["timeout_seconds"] == 1
        assert broker.messages[0]["contacts"] == ["con Lan"]
        await asyncio.sleep(1.6)
        types = [message["type"] for message in broker.messages]
        assert types == ["escalation_armed", "escalation_sent"]
        manager.shutdown()
        database.close()
        return types

    assert asyncio.run(scenario())[0] == "escalation_armed"


def test_recover_republishes_armed_for_pending(tmp_path):
    async def scenario():
        database = Database(f"sqlite:///{tmp_path / 'rearm.db'}")
        database.init_schema()
        event_id = _seed(database)
        crashed = EscalationManager(database, FakeBroker(), FakeNotifier())
        crashed.schedule(event_id, {"urgency": 8})
        crashed.shutdown()

        broker = FakeBroker()
        revived = EscalationManager(database, broker, FakeNotifier())
        assert await revived.recover() == 1
        published = [message["type"] for message in broker.messages]
        revived.shutdown()
        database.close()
        return published

    assert asyncio.run(scenario()) == ["escalation_armed"]


def test_pending_claimed_at_most_once(tmp_path):
    async def scenario():
        database = Database(f"sqlite:///{tmp_path / 'once.db'}")
        database.init_schema()
        event_id = _seed(database)

        seed = EscalationManager(database, FakeBroker(), FakeNotifier())
        assert seed.schedule(event_id, {"urgency": 8})
        seed.shutdown()

        a = EscalationManager(database, FakeBroker(), FakeNotifier())
        b = EscalationManager(database, FakeBroker(), FakeNotifier())
        await a.recover()
        await b.recover()
        await asyncio.sleep(1.8)

        queued = [r for r in database.list_escalation_log() if r["event_id"] == event_id and r["status"] == "queued"]
        leftover = database.list_pending_escalations()
        database.close()
        return len(queued), leftover

    queued_count, leftover = asyncio.run(scenario())
    assert queued_count == 1, "exactly one instance may fire the escalation"
    assert leftover == [], "pending row must be consumed"
